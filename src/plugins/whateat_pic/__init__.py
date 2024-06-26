import base64
import os
import random
import re
from pathlib import Path

import nonebot
import requests
from nonebot import require
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.helpers import extract_image_urls
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.exception import ActionFailed
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import Arg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, on_regex
from nonebot.typing import T_State

from .check_pass import check_cd, check_max

scheduler = require("nonebot_plugin_apscheduler").scheduler

__plugin_meta__ = PluginMetadata(
    name="今天吃什么？",
    description="What to Eat/Drink",
    usage="看下面，注意不要带问号！！！",
    extra={
        "menu_data": [
            {
                "func": "吃什么",
                "trigger_method": "命令: [今|明|后][天|日][早|中|晚][上|午|餐|饭|夜宵|宵夜]吃[什么|啥|点啥]",
                "trigger_condition": "私聊、群聊",
                "brief_des": "查看吃什么，建议看详细说明",
                "detail_des": "列如：\n"
                "今天晚上吃什么\n"
                "明天中午吃啥\n"
                "后天早上吃点啥",
            },
            {
                "func": "喝什么",
                "trigger_method": "命令: [今|明|后][天|日][早|中|晚][上|午|餐|饭|夜宵|宵夜]喝[什么|啥|点啥]",
                "trigger_condition": "私聊、群聊",
                "brief_des": "查看喝什么，建议看详细说明",
                "detail_des": "列如：\n"
                "今天晚上喝什么\n"
                "明天中午喝啥\n"
                "后天早上喝点啥",
            },
            {
                "func": "查看全部菜单",
                "trigger_method": "命令：查[看|寻]全部(菜[单|品]|饮[料|品])",
                "trigger_condition": "私聊、群聊",
                "brief_des": "查看已存的全部菜单，建议看详细说明",
                "detail_des": "例如：\n"
                "查看全部菜单\n"
                "查看全部饮料\n"
                "查看全部菜品\n"
                "查看全部菜单\n"
                "查看全部饮料\n"
                "查寻全部菜品\n"
                "查寻全部饮料\n"
                "查寻全部菜单\n"
                "利用合并消息进行发送，不会刷屏哒！",
            },
        ],
        "menu_template": "default",
    },
)


what_eat = on_regex(
    r"^(/)?[今|明|后]?[天|日]?(早|中|晚)?(上|午|餐|饭|夜宵|宵夜)吃(什么|啥|点啥)$",
    priority=5,
)
what_drink = on_regex(
    r"^(/)?[今|明|后]?[天|日]?(早|中|晚)?(上|午|餐|饭|夜宵|宵夜)喝(什么|啥|点啥)$",
    priority=5,
)
view_all_dishes = on_regex(r"^(/)?查[看|寻]?全部(菜[单|品]|饮[料|品])$", priority=5)
view_dish = on_regex(r"^(/)?查[看|寻]?(菜[单|品]|饮[料|品])[\s]?(.*)?", priority=5)
add_dish = on_regex(
    r"^(/)?添[加]?(菜[品|单]|饮[品|料])[\s]?(.*)?",
    priority=99,
    permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER,
)
del_dish = on_regex(
    r"^(/)?删[除]?(菜[品|单]|饮[品|料])[\s]?(.*)?",
    priority=5,
    permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER,
)

# 今天吃什么路径
img_eat_path = Path(os.path.join(os.path.dirname(__file__), "eat_pic"))
all_file_eat_name = os.listdir(str(img_eat_path))

# 今天喝什么路径
img_drink_path = Path(os.path.join(os.path.dirname(__file__), "drink_pic"))
all_file_drink_name = os.listdir(str(img_drink_path))

# 载入 bot 名字
Bot_NICKNAME = list(nonebot.get_driver().config.nickname)
Bot_NICKNAME = Bot_NICKNAME[0] if Bot_NICKNAME else "脑积水"


@del_dish.handle()
async def _(matcher: Matcher, state: T_State):
    args = list(state["_matched_groups"])
    state["type"] = args[1]
    if args[2]:
        matcher.set_arg("name", args[2])


@del_dish.got("name", prompt="请告诉我你要删除哪个菜品或饮料，发送“取消”可取消操作")
async def _(state: T_State, name: Message = Arg()):
    if str(name) == "取消":
        await del_dish.finish("已取消")
    if state["type"] in ["菜单", "菜品"]:
        img = img_eat_path / f"{str(name)}.jpg"
    elif state["type"] in ["饮料", "饮品"]:
        img = img_drink_path / f"{str(name)}.jpg"

    try:
        os.remove(img)
    except OSError:
        await del_dish.finish(f"不存在该{state['type']}，请检查下菜单再重试吧")
    await del_dish.send(f"已成功删除{state['type']}:{name}", at_sender=True)


@add_dish.handle()
async def _(matcher: Matcher, state: T_State):
    args = list(state["_matched_groups"])
    state["type"] = args[1]
    if args[2]:
        matcher.set_arg("dish_name", args[2])


@add_dish.got("dish_name", prompt="⭐请发送名字\n发送“取消”可取消添加")
async def _(state: T_State, dish_name: Message = Arg()):
    state["name"] = str(dish_name)
    if str(dish_name) == "取消":
        await add_dish.finish("已取消")


@add_dish.got("img", prompt="⭐图片也发给我吧\n发送“取消”可取消添加")
async def _(state: T_State, img: Message = Arg()):
    if str(img) == "取消":
        await add_dish.finish("已取消")
    img_url = extract_image_urls(img)
    if not img_url:
        await add_dish.finish("没有找到图片 (╯▔皿▔)╯，请稍后重试", at_sender=True)

    if state["type"] in ["菜品", "菜单"]:
        path = img_eat_path
    elif state["type"] in ["饮料", "饮品"]:
        path = img_drink_path

    dish_img = requests.get(url=img_url[0], timeout=5)
    with open(os.path.join(path, str(state["name"] + ".jpg")), "wb") as f:
        f.write(dish_img.content)
    await add_dish.finish(
        f"成功添加{state['type']}:{state['name']}\n{MessageSegment.image(img_url[0])}"
    )


@view_dish.handle()
async def _(matcher: Matcher, state: T_State):
    # 正则匹配组
    args = list(state["_matched_groups"])

    if args[1] in ["菜单", "菜品"]:
        state["type"] = "吃的"
    elif args[1] in ["饮料", "饮品"]:
        state["type"] = "喝的"

    # 设置下一步 got 的 arg
    if args[2]:
        matcher.set_arg("name", args[2])


@view_dish.got("name", prompt=f"请告诉{Bot_NICKNAME}具体菜名或者饮品名吧")
async def _(state: T_State, name: Message = Arg()):
    if state["type"] == "吃的":
        img = img_eat_path / f"{str(name)}.jpg"
    elif state["type"] == "喝的":
        img = img_drink_path / f"{str(name)}.jpg"

    try:
        await view_dish.send(MessageSegment.image(img))
    except ActionFailed:
        await view_dish.finish("没有找到你所说的，请检查一下菜单吧", at_sender=True)


@view_all_dishes.handle()
async def _(bot: Bot, event: MessageEvent, state: T_State):
    # 正则匹配组
    path = ""
    args = list(state["_matched_groups"])
    if args[1] in ["菜单", "菜品"]:
        path = img_eat_path
        all_name = all_file_eat_name
    elif args[1] in ["饮料", "饮品"]:
        path = img_drink_path
        all_name = all_file_drink_name

    # 合并转发
    msg_list = [f"{Bot_NICKNAME}查询到的{args[1]}如下"]
    for N, name in enumerate(all_name, start=1):
        img = os.path.join(path, name)
        with open(img, "rb") as im:
            img_bytes = im.read()
        base64_str = f"base64://{base64.b64encode(img_bytes).decode()}"
        name = re.sub(".jpg", "", name)
        msg_list.append(f"{N}.{name}\n{MessageSegment.image(base64_str)}")
    await send_forward_msg(bot, event, Bot_NICKNAME, bot.self_id, msg_list)


# 初始化内置时间的 last_time
time = 0
# 用户数据
user_count = {}


@what_drink.handle()
async def wtd(msg: MessageEvent):  # sourcery skip: use-fstring-for-concatenation
    global time, user_count
    check_result, remain_time, new_last_time = check_cd(time)
    if not check_result:
        time = new_last_time
        await what_drink.finish(f"cd 冷却中，还有{remain_time}秒", at_sender=True)
    else:
        is_max, user_count = check_max(msg, user_count)
        if is_max:
            await what_drink.finish(random.choice(max_msg), at_sender=True)
        time = new_last_time
        img_name = random.choice(all_file_drink_name)
        img = img_drink_path / img_name
        with open(img, "rb") as im:
            img_bytes = im.read()
        base64_str = "base64://" + base64.b64encode(img_bytes).decode()
        result_msg = (
            f"{Bot_NICKNAME}建议你喝：\n⭐{img.stem}⭐\n"
            + MessageSegment.image(base64_str)
        )
        try:
            await what_drink.send(f"{Bot_NICKNAME}正在为你找好喝的……")
            await what_drink.send(result_msg, at_sender=True)
        except ActionFailed:
            await what_drink.finish("出错啦！没有找到好喝的~")


@what_eat.handle()
async def wte(msg: MessageEvent):  # sourcery skip: use-fstring-for-concatenation
    global time, user_count
    check_result, remain_time, new_last_time = check_cd(time)
    if not check_result:
        time = new_last_time
        await what_eat.finish(f"cd 冷却中，还有{remain_time}秒", at_sender=True)
    else:
        is_max, user_count = check_max(msg, user_count)
        if is_max:
            await what_eat.finish(random.choice(max_msg), at_sender=True)
        time = new_last_time
        img_name = random.choice(all_file_eat_name)
        img = img_eat_path / img_name
        with open(img, "rb") as im:
            img_bytes = im.read()
        base64_str = "base64://" + base64.b64encode(img_bytes).decode()
        result_msg = (
            f"{Bot_NICKNAME}建议你吃：\n⭐{img.stem}⭐\n"
            + MessageSegment.image(base64_str)
        )
        try:
            await what_eat.send(f"{Bot_NICKNAME}正在为你找好吃的……")
            await what_eat.send(result_msg, at_sender=True)
        except ActionFailed:
            await what_eat.finish("出错啦！没有找到好吃的~")


# ~~~~~~~~~~~~~~~~~~~~~~~~~~~分割区~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# 诶嘿你发现了宝藏>.<
# 这里啥也没有，嘿嘿
# 有机会再在这里写点东西吧，嘿嘿

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~分割区~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


# 每日 0 点重置用户数据
def reset_user_count():
    global user_count
    user_count = {}


try:
    scheduler.add_job(reset_user_count, "cron", hour="0", id="delete_date")
except ActionFailed as e:
    logger.warning(f"定时任务添加失败，{repr(e)}")


# 上限回复消息
max_msg = (
    "你今天吃的够多了！不许再吃了 (´-ωก`)",
    "吃吃吃，就知道吃，你都吃饱了！明天再来 (▼皿▼#)",
    "(*｀へ´*) 你猜我会不会再给你发好吃的图片",
    f"没得吃的了，{Bot_NICKNAME}的食物都被你这坏蛋吃光了！",
    "你在等我给你发好吃的？做梦哦！你都吃那么多了，不许再吃了！ヽ (≧Д≦) ノ",
)


# 调用合并转发 api 函数
async def send_forward_msg(
    bot: Bot,
    event: MessageEvent,
    name: str,
    uin: str,
    msgs: list,
) -> dict:
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
