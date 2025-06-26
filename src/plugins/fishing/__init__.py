import asyncio
import random

from nonebot import get_driver, on_command, on_fullmatch
from nonebot.adapters import Event, Message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.adapters.onebot.v11.helpers import (
    Cooldown,
    CooldownIsolateLevel,
)
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .config import Config, config
from .data_source import (
    choice,
    get_backpack,
    get_balance,
    get_quality,
    get_stats,
    get_switch_fish,
    save_fish,
    sell_all_fish,
    sell_fish,
    sell_quality_fish,
    switch_fish,
    update_sql,
)
from .data_source import fish as fish_quality

__plugin_meta__ = PluginMetadata(
    name="赛博钓鱼",
    description="你甚至可以电子钓鱼",
    usage="发送“钓鱼”，放下鱼竿。",
    type="application",
    homepage="https://github.com/C14H22O/nonebot-plugin-fishing",
    config=Config,
    supported_adapters=None,
)

Bot_NICKNAME: str = next(iter(get_driver().config.nickname), "姚奕")
fishing = on_fullmatch(("fishing", "钓鱼"), block=True)
stats = on_fullmatch(("stats", "统计信息"), block=True)
backpack = on_fullmatch(("backpack", "背包"), block=True)
sell = on_command("sell", aliases={"卖鱼"}, block=True)
balance = on_fullmatch(("balance", "余额"), block=True)
switch = on_fullmatch(
    ("fish_switch", "开关钓鱼"),
    permission=GROUP_OWNER | GROUP_ADMIN | SUPERUSER,
    block=True,
)
update_def = on_fullmatch("update", permission=SUPERUSER, block=True)


@update_def.handle()
async def _update(event: Event):
    """更新"""
    await update_sql()
    await update_def.finish("更新成功！")


@fishing.handle(
    parameterless=[
        Cooldown(
            cooldown=config.fishing_limit,
            prompt="河累了，休息一下吧",
            isolate_level=CooldownIsolateLevel.USER,
        )
    ]
)
async def _fishing(event: GroupMessageEvent | PrivateMessageEvent, bot: Bot):
    """钓鱼"""
    if isinstance(event, GroupMessageEvent) and not await get_switch_fish(event):
        await fishing.finish("钓鱼在本群处于关闭状态，请看菜单重新打开")

    user_id = event.get_user_id()
    fish = await choice(user_id=user_id)
    await bot.set_msg_emoji_like(
        message_id=event.message_id,
        emoji_id="127881",
    )

    fish_name = fish[0]
    fish_long = fish[1]
    sleep_time = random.randint(1, 6)
    result = ""
    if fish_name == "河":
        result = "* 河累了，休息..等等...你钓到了一条河？！"
    elif fish_name == "尚方宝剑":
        result = f"* 你钓到了一把 {get_quality(fish_name)} {fish_name}，长度为 {fish_long}cm！"
    elif fish_name == "Mr.ling":
        result = "* 你钓到了一条...等等...我没看错吧？！你竟然钓到了一条 Mr.ling？！"
    else:
        result = f"* 你钓到了一条 {get_quality(fish_name)} {fish_name}，长度为 {fish_long}cm！"
    await save_fish(user_id, fish_name, fish_long)
    await asyncio.sleep(sleep_time)
    await fishing.finish(result, reply_message=True)


@stats.handle()
async def _stats(event: Event):
    """统计信息"""
    user_id = event.get_user_id()
    await stats.finish(await get_stats(user_id), reply_message=True)


@backpack.handle()
async def _backpack(bot: Bot, event: MessageEvent):
    """背包"""
    user_id = event.get_user_id()
    fmt = await get_backpack(user_id)
    return (
        await backpack.send(fmt)
        if isinstance(fmt, str)
        else await send_forward_msg(bot, event, Bot_NICKNAME, bot.self_id, fmt)
    )


@sell.handle()
async def _sell(event: Event, arg: Message = CommandArg()):
    """卖鱼"""
    msg = arg.extract_plain_text()
    user_id = event.get_user_id()
    if msg == "":
        await sell.finish("请输入要卖出的鱼的名字，如：卖鱼 小鱼")
    if msg == "全部":
        await sell.finish(await sell_all_fish(user_id), reply_message=True)
    if msg in fish_quality.keys():  # 判断是否是为品质
        await sell.finish(await sell_quality_fish(user_id, msg), reply_message=True)
    await sell.finish(await sell_fish(user_id, msg), reply_message=True)


@balance.handle()
async def _balance(event: Event):
    """余额"""
    user_id = event.get_user_id()
    await balance.finish(await get_balance(user_id), reply_message=True)


@switch.handle()
async def _switch(event: GroupMessageEvent | PrivateMessageEvent):
    """钓鱼开关"""
    if await switch_fish(event):
        await switch.finish("钓鱼 已打开")
    else:
        await switch.finish("钓鱼 已关闭")


async def send_forward_msg(
    bot: Bot,
    event: MessageEvent,
    name: str,
    uin: str,
    msgs: list,
) -> dict:
    """
    发送转发消息的异步函数。

    参数:
        bot (Bot): 机器人实例
        event (MessageEvent): 消息事件
        name (str): 转发消息的名称
        uin (str): 转发消息的 UIN
        msgs (list): 转发的消息列表

    返回:
        dict: API 调用结果
    """

    def to_json(msg: Message):
        return {"type": "node", "data": {"name": name, "uin": uin, "content": msg}}

    messages = [to_json(msg) for msg in msgs]
    if isinstance(event, GroupMessageEvent):
        return await bot.send_group_forward_msg(
            group_id=event.group_id, messages=messages
        )
    return await bot.send_private_forward_msg(user_id=event.user_id, messages=messages)
