import asyncio
import datetime
import os
import random
import re
import time

import aiofiles
import nonebot
import ujson
from nonebot import get_plugin_config, logger, on_command, on_message
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, MessageEvent, Reply
from nonebot.adapters.onebot.v11.helpers import (
    Cooldown,
    CooldownIsolateLevel,
)
from nonebot.adapters.onebot.v11.utils import unescape
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_apscheduler import scheduler

from U1.database import (
    Channel,
)

from .config import Config, ai_config
from .utils import (
    call_tools,
    chat_with_gpt,
    extract_mface_summary,
    get_intent,
    is_image_message,
    replace_at_message,
    replace_cq_with_caption,
)

__plugin_meta__ = PluginMetadata(
    name="aichat",
    description="ai聊天",
    usage="nope",
    config=Config,
)


config = get_plugin_config(Config)


datadir = ai_config.data_dir
os.makedirs(datadir, exist_ok=True)
truncate_probs = [0.1, 0.1]
MAX_LEN = 12
bracket_probs = [0.25, 0.3]
unreplied_msg: dict[str, int] = {}


async def is_record(event: GroupMessageEvent, bot: Bot) -> bool:
    message = str(event.get_message())
    if event.reply:
        message += str(event.reply)
    return (
        event.group_id in ai_config.record_group
        and "[CQ:video" not in message
        and not event.to_me
        and "clean.session" not in message
        and await Channel.filter(
            guildId=str(event.group_id), assignee=bot.self_id
        ).exists()
    )


async def is_use(event: GroupMessageEvent, bot: Bot) -> bool:
    message = str(event.get_message())
    return (
        event.group_id in ai_config.record_group
        and "[CQ:video" not in message
        and await Channel.filter(
            guildId=str(event.group_id), assignee=bot.self_id
        ).exists()
    )


clean_command = on_command("clean.session", permission=SUPERUSER, block=True)
record_msg = on_message(rule=is_record)
handle_command = on_message(rule=is_use & to_me())


async def load_or_init_data(group_id: str) -> dict:
    file_path = os.path.join(datadir, f"{group_id}.json")
    if not os.path.exists(file_path):
        # 获取锁，如果文件锁不存在，为它创建一个
        if group_id not in file_locks:
            file_locks[group_id] = asyncio.Lock()

        async with file_locks[group_id]:
            async with aiofiles.open(file_path, "w") as f:
                await f.write(
                    ujson.dumps(
                        {
                            "keep_prompt": [],
                            "record": [],
                        },
                        ensure_ascii=False,
                    )
                )
    # 获取锁，如果文件锁不存在，为它创建一个
    if group_id not in file_locks:
        file_locks[group_id] = asyncio.Lock()

    async with file_locks[group_id]:
        async with aiofiles.open(file_path) as f:
            data = ujson.loads(await f.read())

    data["keep_prompt"] = [
        {"role": "system", "content": ai_config.prompt},
    ]
    return data


file_locks = {}


async def save_data(group_id: str, data: dict) -> None:
    file_path = os.path.join(datadir, f"{group_id}.json")

    # 获取锁，如果文件锁不存在，为它创建一个
    if group_id not in file_locks:
        file_locks[group_id] = asyncio.Lock()
    async with file_locks[group_id]:
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            json_data = ujson.dumps(data, indent=4, ensure_ascii=False)
            await f.write(json_data)


def format_time(event_time: int) -> str:
    return (
        f"[{datetime.datetime.fromtimestamp(event_time).strftime('%Y-%m-%d %H:%M:%S')}]"
    )


async def create_process_text(
    event: GroupMessageEvent, text: str, time_now: str
) -> str:
    nickname = event.sender.nickname
    user_id = event.get_user_id()
    text = unescape(text)  # 反转义

    # 处理文本中的 CQ 码
    text = await process_cq_code(text, event)
    text = replace_at_message(text=text)
    logger.info(f"{event.message!r}")
    if event.reply:
        return await process_reply(event.reply, text, time_now, nickname, user_id)

    return f"{time_now} {nickname}({user_id}): {text}"


async def process_cq_code(text: str, event: MessageEvent | Reply) -> str:
    """处理文本中的 CQ 码，包括 mface 和 image 类型。"""
    if "[CQ:mface" in text:
        text = extract_mface_summary(text)
    elif "[CQ:image" in text:
        is_image, image_url = is_image_message(event, True)
        if is_image and ai_config.enable_ofa_image:
            caption: str = "图片"
            text = replace_cq_with_caption(text, caption)
    return text


async def process_reply(
    event: Reply, text: str, time_now: str, nickname: str | None, user_id: str
) -> str:
    """处理回复消息的格式化。"""
    reply_user_id = event.sender.user_id
    reply_nickname = event.sender.nickname
    logger.info(f"{event.message!r}")
    reply_text = str(event.message).strip()

    reply_text = await process_cq_code(reply_text, event)
    reply_text = replace_at_message(reply_text)
    return (
        f"{time_now} {nickname}({user_id}) 引用并回复了 "
        f"{reply_nickname}({reply_user_id}) 的消息：\n"
        f"引用内容：“{reply_text}”\n"
        f"回复内容：“{text}”"
    )


@clean_command.handle()
async def _(event: GroupMessageEvent) -> None:
    group_id = str(event.group_id)
    file_path = os.path.join(datadir, f"{group_id}.json")
    if os.path.exists(file_path):
        os.remove(file_path)
        unreplied_msg.pop(group_id, None)
        await clean_command.finish("脑袋空空！")
    await clean_command.finish("欸，我不记得有和你们聊过天啊?")


def add_element(my_list: list, keep_num=50) -> list:
    return my_list[-keep_num:]


def split_sentences(reply: str) -> list[str]:
    # 去掉头尾的标点符号并分割句子
    reply = reply.strip(r"""”“’‘"'!！。.~""")
    sentences = re.split("[，。~]", reply)

    # # 根据概率删减句子，优化后移除循环中多余的异常处理
    # for prob in truncate_probs:
    #     if len(sentences) > 2 and random.random() < prob:
    #         sentences.pop()

    # 根据概率添加括号
    if sentences:
        rand = random.random()
        if rand < bracket_probs[0]:
            sentences[-1] += "（）"
        elif rand < bracket_probs[1]:
            sentences[-1] += "（"

    # 限制输出的句子数量
    return sentences[:MAX_LEN]


def get_type_time(string) -> float:
    """
    打字时间模拟，中英文区别计算
    """
    tpc_english = 0.2  # 英文字符打字时间
    tpc_chinese = 0.65  # 中文字符打字时间
    return sum(
        tpc_chinese if "\u4e00" <= char <= "\u9fff" else tpc_english for char in string
    )


async def send_with_dynamic_wait(sentence: str, event, bot: Bot):
    # 动态计算等待时间，假设每个字符等待 0.05 秒
    tying_time = get_type_time(sentence)
    await asyncio.sleep(tying_time)
    await bot.send(event, sentence)


@handle_command.handle(
    parameterless=[
        Cooldown(
            cooldown=2,
            prompt="太快了...",
            isolate_level=CooldownIsolateLevel.USER,
        )
    ]
)
async def send_ai_msg(event: GroupMessageEvent, bot: Bot):
    time_question = time.time()
    group_id = str(event.group_id)
    unreplied_msg[group_id] = 0
    text = str(event.get_message()).strip()
    if not text:
        await bot.send(event, "讲话啊喂！", reply_message=True)
        return

    data = await load_or_init_data(group_id)
    keep_prompt: list = data.get("keep_prompt", [])

    # 获取50条记录
    record: list = data.get("record", [])

    time_now = format_time(event.time)
    process_text = await create_process_text(event, text, time_now)
    process_text = "> 响应该聊天记录：\n" + process_text
    # record.extend(
    #     (
    #         {"role": "user", "content": process_text},
    #         {
    #             "role": "user",
    #             "content": "请用自己的人设，响应最近的消息，消息选取时间不要太大",
    #         },
    #     )
    # )
    record.append({"role": "user", "content": process_text})
    response = await chat_with_gpt(keep_prompt + record, ai_config)
    if response.tool_calls:
        if result := await call_tools(response.tool_calls[0]):
            await bot.send(event, "处理中...", reply_message=True)
            record.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [response.tool_calls[0].to_dict()],
                }
            )
            record.append(result)
            response = await chat_with_gpt(keep_prompt + record, ai_config)
            record.append({"role": "assistant", "content": response.content})
            await process_response(event, bot, time_question, response.content)
    else:
        record.append({"role": "assistant", "content": response.content})
        await process_response(event, bot, time_question, response.content)

    # 保持记录在50条以内
    record = add_element(record, ai_config.record_num)

    # 保存记录
    data["record"] = record
    await save_data(group_id, data)


async def process_response(event, bot, time_question, response):
    if ai_config.sentences_divide:
        response = split_sentences(response)
        logger.info(response)
        time_get_answer: float = time.time()
        if time_get_answer - time_question <= get_type_time(response[0]) + 1:
            # 否则按照打字时间延迟发送
            await asyncio.sleep(
                get_type_time(response[0]) + 1 - (time_get_answer - time_question)
            )
        await bot.send(event, response[0], reply_message=True)
        for sentence in response[1:]:
            await send_with_dynamic_wait(sentence, event, bot)
    else:
        await send_with_dynamic_wait(response, event, bot)


QUESTION_KEYWORDS = [
    "什么",
    "如何",
    "谁",
    "哪",
    "为什么",
    "怎么办",
    "呢",
    "那么",
    "可以",
    "问",
    "吗",
]


def is_question(message: str) -> bool:
    """
    判断消息是否为询问。
    Args:
    - message (str): 消息文本。

    Returns:
    - bool: 如果是询问则返回 True，否则返回 False。
    """
    # 检查是否以问号结尾
    if message.endswith("?") or message.endswith("？"):
        return True

    # 检查是否包含关键词
    return any(keyword in message for keyword in QUESTION_KEYWORDS)


@record_msg.handle()
async def _(event: GroupMessageEvent, bot: Bot):
    group_id = str(event.group_id)

    data = await load_or_init_data(group_id)
    record: list = data.get("record", [])

    text = str(event.get_message()).strip()
    time_now = format_time(event.time)
    process_text = await create_process_text(event, text, time_now)

    record.append({"role": "user", "content": "聊天记录: \n" + process_text})
    # 保持记录在50条以内
    record = add_element(record, ai_config.record_num)
    data["record"] = record
    await save_data(group_id, data)
    # 判断是否为图片，不是则记录计数器
    if (
        "[CQ:file" not in text
        and "[CQ:video" not in text
        and "[CQ:mface" not in text
        and "[CQ:image" not in text
        and int(group_id) in ai_config.record_group
    ):
        unreplied_msg[group_id] = unreplied_msg.get(group_id, 0) + 1
        logger.info(f"unreplied_msg: {unreplied_msg}")

        # 动态调整回复概率
        reply_prob = dynamic_reply_probability(group_id)
        logger.info(f"reply_prob: {reply_prob}")
        # 未回复消息超过随机设定的阈值时，决定是否回复
        if unreplied_msg[group_id] > 3 and random.random() < reply_prob:
            history = await get_history(bot, group_id)
            history_text = "".join(
                f"{msg.get_user_id()}: {msg.get_message()}\n" for msg in history
            )
            if await get_intent(history_text, bot.self_id):
                unreplied_msg[group_id] = 0
                await send_ai_msg(event, bot)  # 调用 AI 回复函数
            return
        elif unreplied_msg[group_id] <= 1 and is_question(text):
            unreplied_msg[group_id] = 0
            await send_ai_msg(event, bot)  # 调用 AI 回复函数
            return


def dynamic_reply_probability(group_id: str) -> float:
    """
    根据时间段和未回复消息数量动态计算回复概率。
    低活跃时段（深夜）回复概率较低，白天或活跃时段回复概率适中。
    """
    current_hour: int = datetime.datetime.now().hour

    # 根据时间段设置基础概率
    if 0 <= current_hour < 6:
        base_prob = 0.03  # 深夜时段，回复概率较低
    elif 6 <= current_hour < 18:
        base_prob = 0.07  # 白天时段，回复概率适中
    else:
        base_prob = 0.05  # 晚上时段，回复概率适中偏低

    # 根据该群未回复消息数量动态调整概率
    unreplied_count: int = unreplied_msg.get(group_id, 0)  # 获取该群的未回复消息数
    if unreplied_count > 30:
        return min(0.15, base_prob + 0.05)
    elif unreplied_count >= 10:
        return base_prob + 0.03
    else:
        return base_prob


async def get_history(
    bot: Bot, group_id: str, cout: int = 30
) -> list[GroupMessageEvent]:
    data: list[dict] = (await bot.get_group_msg_history(group_id=group_id, count=cout))[
        "messages"
    ]
    new_data: list[GroupMessageEvent] = [GroupMessageEvent(**i) for i in data]
    return new_data


async def send_time_topic(temp_topic: str):
    bots = nonebot.get_bots()
    # 构建系统消息，发送到群里
    for group_id in ai_config.record_group:
        data = await load_or_init_data(group_id=str(group_id))
        keep_prompt: list = data.get("keep_prompt", [])
        record: list = data.get("record", [])
        time_now: str = format_time(int(time.time()))
        record.append(
            {
                "role": "user",
                "content": f"现在时间：{time_now} 请你做该事件：{temp_topic}",
            }
        )
        response = await chat_with_gpt(keep_prompt + record, ai_config)
        record.append({"role": "assistant", "content": response.content})
        data["record"] = record
        for bot in bots.values():
            if await Channel.filter(
                guildId=str(group_id), assignee=str(bot.self_id)
            ).exists():
                await bot.send_group_msg(group_id=group_id, message=response.content)
                break
        await save_data(str(group_id), data)


for k, v in ai_config.time_topic.items():
    scheduler.add_job(
        send_time_topic,
        "cron",
        hour=k,
        minute=0,
        second=0,
        args=[v],
        misfire_grace_time=120,
    )
