import random

from nonebot import get_driver, logger, on_command, on_fullmatch
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.adapters.onebot.v11.helpers import extract_image_urls
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select

from .models import cave_models
from .tool import is_image_message

nickname_list = list(get_driver().config.nickname)
Bot_NICKNAME = nickname_list[0] if nickname_list else "bot"
__plugin_meta__ = PluginMetadata(
    name="回声洞",
    description="看看别人的投稿，也可以自己投稿~",
    usage="""投稿\n
查看回声洞记录\n
删除 [序号]\n
如：\n
投稿""",
)


cave_main = on_fullmatch("回声洞", block=True)
cave_add = on_command("投稿", aliases={"回声洞投稿"}, block=True)
cave_am_add = on_command("匿名投稿", aliases={"回声洞匿名投稿"}, block=True)
cave_history = on_command("查看回声洞记录", aliases={"回声洞记录"}, block=True)
cave_view = on_command("查看", block=True)
cave_del = on_command("删除", block=True)

cave_update = on_command("更新回声洞", permission=SUPERUSER, block=True)
SUPERUSER_list = list(get_driver().config.superusers)


@cave_update.handle()
async def _():
    "操作数据库，将id重新排列，并且自动id更新到最新"
    async with get_session() as session:
        # 获取所有记录
        stmt = select(cave_models)
        result = await session.execute(stmt)
        all_caves = result.scalars().all()

        # 使用集合来跟踪已处理的详情
        seen_details = set()
        new_caves = []

        # 遍历所有对象，移除重复项
        for cave in all_caves:
            if cave.details not in seen_details:
                seen_details.add(cave.details)
                new_caves.append(cave)

        # 提示信息
        await cave_update.send(
            f"共有{len(all_caves)}条记录，{len(new_caves)}条不重复记录"
        )

        # 删除所有记录
        await session.execute(delete(cave_models))

        # 保存新的对象
        for index, cave in enumerate(new_caves, start=1):
            new_cave = cave_models(
                id=index, details=cave.details, user_id=cave.user_id, time=cave.time
            )
            session.add(new_cave)
        await session.commit()

        # 重新获取所有记录
        stmt = select(cave_models)
        result = await session.execute(stmt)
        all_caves = result.scalars().all()

        new_cave = []
        # 重新排列并创建新的对象
        for cave in all_caves:
            details = cave.details
            user_id = cave.user_id
            time = cave.time
            anonymous = cave.anonymous
            new_cave.append((details, user_id, time, anonymous))

        # 按照time排序
        new_cave = sorted(new_cave, key=lambda x: x[2], reverse=False)

        # 删除所有记录
        await session.execute(delete(cave_models))

        # 重新创建排序后的记录
        for index, (details, user_id, time, anonymous) in enumerate(new_cave, start=1):
            sorted_cave = cave_models(
                id=index,
                details=details,
                user_id=user_id,
                time=time,
                anonymous=anonymous,
            )
            session.add(sorted_cave)
        await session.commit()

    await cave_update.finish("更新成功！")


async def condition(event: MessageEvent, key: str) -> tuple[bool, str | None]:
    "判断是否符合投稿条件"
    urllist = extract_image_urls(event.get_message())
    if len(urllist) > 1:
        return False, "只能投一张图哦"
    if not isinstance(event, PrivateMessageEvent):
        return False, "别搞啊，只能私聊我才能投稿啊！"
    if not key:
        return False, "不输入内容，小子你是想让我投稿什么？空气咩？"
    if len(key) < 6:
        return False, "字数太少了！"
    return True, None


@cave_add.handle()
async def _(bot: Bot, event: MessageEvent):
    is_image = await is_image_message(event)
    details = is_image[1] if is_image[0] else str(event.get_message())
    details = details.replace("投稿", "", 1).strip()
    result = await condition(event, details)
    if result[0] is False:  # 审核
        await cave_add.finish(result[1])

    async with get_session() as session:
        caves = cave_models(details=details, user_id=event.user_id)
        session.add(caves)
        await session.commit()
        await session.refresh(caves)

        result = f"预览：\n编号:{caves.id}\n"
        result += "----------------------\n"
        result += f"内容：\n{caves.details}\n"
        result += "----------------------\n"
        result += f"投稿时间：{caves.time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += "----------------------"
        for i in SUPERUSER_list:
            await bot.send_private_msg(
                user_id=int(i),
                message=Message(f"来自用户{event.get_user_id()}\n{result}"),
            )
        await cave_add.finish(Message(f"投稿成功！\n{result}"))


@cave_am_add.handle()
async def _(bot: Bot, event: MessageEvent):
    "匿名发布回声洞"
    is_image = await is_image_message(event)
    details = is_image[1] if is_image[0] else str(event.get_message())
    details = details.replace("匿名投稿", "", 1).strip()
    result = await condition(event, details)
    if result[0] is False:  # 审核
        await cave_add.finish(result[1])

    async with get_session() as session:
        caves = cave_models(details=details, user_id=event.user_id, anonymous=True)
        session.add(caves)
        await session.commit()
        await session.refresh(caves)

        result = f"预览：\n编号:{caves.id}\n"
        result += "----------------------\n"
        result += f"内容：\n{caves.details}\n"
        result += "----------------------\n"
        result += f"投稿时间：{caves.time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += "----------------------\n"
        result += "匿名投稿将会保存用户信息\n但其他用户无法看到作者"
        for i in SUPERUSER_list:
            await bot.send_private_msg(
                user_id=int(i),
                message=Message(f"来自用户{event.get_user_id()}\n{result}"),
            )
        await cave_add.finish(Message(f"匿名投稿成功！\n{result}"))


@cave_del.handle()
async def _(bot: Bot, event: MessageEvent):
    Message_text = str(event.message)
    deletion_reasons = extract_deletion_reason(Message_text)
    key = deletion_reasons["序号"]
    # 如果有原因获取，没有为 none
    reason = deletion_reasons["原因"]
    try:
        key = int(key)
    except ValueError:
        await cave_del.finish("请输入正确的序号")

    async with get_session() as session:
        try:
            stmt = select(cave_models).where(cave_models.id == key)
            result = await session.execute(stmt)
            data = result.scalar_one()
        except Exception:
            await cave_del.finish("没有这个序号的投稿")

        # 判断是否是超级用户或者是投稿人
        if str(event.user_id) in SUPERUSER_list:
            try:
                await bot.send_private_msg(
                    user_id=data.user_id,
                    message=Message(
                        f"你的投稿{key}已经被{event.user_id}删除了！\n内容为：\n{data.details}\n原因：{reason}"
                    ),
                )
            except Exception:
                logger.exception(
                    f"回声洞删除投稿私聊通知失败，投稿人 id：{data.user_id}"
                )
                await cave_del.send("删除失败，私聊通知失败")
        elif event.user_id == data.user_id:
            result_content = data.details
            await session.delete(data)
            await session.commit()
            await cave_del.finish(
                Message(
                    f"删除成功！编号{key}的投稿已经被删除！\n内容为：\n{result_content}"
                )
            )
        else:
            await cave_del.finish("你不是投稿人，也不是作者的，你想干咩？")

        result_content = data.details
        await session.delete(data)
        await session.commit()
        await cave_del.finish(
            Message(
                f"删除成功！编号{key}的投稿已经被删除！\n内容为：\n{result_content}\n原因：{reason}"
            )
        )


@cave_main.handle()
async def _():
    async with get_session() as session:
        stmt = select(cave_models)
        result = await session.execute(stmt)
        all_caves = result.scalars().all()

        if not all_caves:
            await cave_main.finish("暂时没有投稿哦~")

        random_cave = random.choice(all_caves)
        displayname = (
            "***（匿名投稿）" if random_cave.anonymous else random_cave.user_id
        )
        result = f"编号:{random_cave.id}\n"
        result += "----------------------\n"
        result += f"内容：\n{random_cave.details}\n"
        result += "----------------------\n"
        result += f"投稿人：{displayname}\n"
        result += f"投稿时间：{random_cave.time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += "----------------------\n"
        result += "可以私聊我投稿内容啊！\n投稿 [内容]（支持图片，文字）\n匿名投稿 [内容]（支持图片，文字）"
        await cave_main.finish(Message(result))


@cave_view.handle()
async def _(args: Message = CommandArg()):
    key = str(args).strip()
    if not key:
        await cave_view.finish("请输入编号")

    async with get_session() as session:
        stmt = select(cave_models).where(cave_models.id == int(key))
        result = await session.execute(stmt)
        cave = result.scalar_one_or_none()

        if cave is None:
            await cave_view.finish("没有这个序号的投稿")

        # 判断是否是匿名
        displayname = "***（匿名投稿）" if cave.anonymous else cave.user_id
        result = f"编号:{cave.id}\n"
        result += "----------------------\n"
        result += f"内容：\n{cave.details}\n"
        result += "----------------------\n"
        result += f"投稿人：{displayname}\n"
        result += f"投稿时间：{cave.time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += "----------------------\n"
        result += "可以私聊我投稿内容啊！\n投稿 [内容]（支持图片，文字）\n匿名投稿 [内容]（支持图片，文字）"
        await cave_view.finish(Message(result))


@cave_history.handle()
async def _(bot: Bot, event: MessageEvent):
    # 查询 userid 写所有数据
    async with get_session() as session:
        stmt = select(cave_models).where(cave_models.user_id == event.user_id)
        result = await session.execute(stmt)
        all_caves = result.scalars().all()

        msg_list = [
            "回声洞记录如下：",
            *[
                Message(
                    f"----------------------\n编号：{i.id}\n----------------------\n内容：\n{i.details}\n----------------------\n投稿时间：{i.time.strftime('%Y-%m-%d %H:%M:%S')}\n----------------------"
                )
                for i in all_caves
            ],
        ]
        await send_forward_msg(bot, event, Bot_NICKNAME, bot.self_id, msg_list)


async def send_forward_msg(
    bot: Bot,
    event: MessageEvent,
    name: str,
    uin: str,
    msgs: list,
) -> dict:
    """
    发送转发消息的异步函数。

    参数：
        bot (Bot): 机器人实例
        event (MessageEvent): 消息事件
        name (str): 转发消息的名称
        uin (str): 转发消息的 UIN
        msgs (list): 转发的消息列表

    返回：
        dict: API 调用结果
    """

    def to_json(msg: Message):
        return {"type": "node", "data": {"name": name, "uin": uin, "content": msg}}

    messages = [to_json(msg) for msg in msgs]
    if isinstance(event, GroupMessageEvent):
        return await bot.call_api(
            "send_group_forward_msg", group_id=event.group_id, messages=messages
        )
    return await bot.call_api(
        "send_private_forward_msg", user_id=event.user_id, messages=messages
    )


def extract_deletion_reason(text):
    """
    从文本中提取删除原因，处理“删除1”或“删除 1 原因1”等格式。

    Args:
        text (str): 包含删除原因的文本。

    Returns:
        dict: 包含删除原因的字典，包含序号和原因。

    Example:
        >>> text = "删除1 原因1"
        >>> extract_deletion_reason(text)
        {'序号': 1, '原因': '原因1'}
    """
    # 移除 "删除" 关键字以及多余的空格
    cleaned_text = text.replace("删除", "", 1).strip()

    # 分离序号和原因
    num = ""
    reason = ""

    # 通过第一个非数字字符来划分序号和原因
    for idx, char in enumerate(cleaned_text):
        if char.isdigit():
            num += char
        else:
            # 当遇到第一个非数字字符时，余下部分全是原因
            reason = cleaned_text[idx:].strip()
            break

    # 若没有原因，则设为默认值 "作者删除"
    if not reason:
        reason = "作者删除"

    return {"序号": int(num), "原因": reason}
