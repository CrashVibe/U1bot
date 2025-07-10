import asyncio
import random

from nonebot import get_driver, on_command, on_fullmatch
from nonebot.adapters import Event
from nonebot.adapters.milky import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.adapters.milky.event import FriendMessageEvent, GroupMessageEvent
from nonebot.adapters.milky.message import OutgoingForwardedMessage
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from U1.utils.permission import GROUP_ADMIN, GROUP_OWNER
from U1.utils.token_bucket import (
    Cooldown,
    CooldownIsolateLevel,
)

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
async def _fishing(event: GroupMessageEvent | FriendMessageEvent, bot: Bot):
    """钓鱼"""
    if isinstance(event, GroupMessageEvent) and not await get_switch_fish(event):
        await fishing.finish("钓鱼在本群处于关闭状态，请看菜单重新打开")

    user_id = event.get_user_id()
    fish = await choice(user_id=user_id)
    await bot.send_group_message_reaction(
        group_id=event.data.peer_id,
        message_seq=event.message_id,
        reaction="127881",
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
    await fishing.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                MessageSegment.text(result),
            ],
        ),
    )


@stats.handle()
async def _stats(event: MessageEvent):
    """统计信息"""
    user_id = event.get_user_id()

    await stats.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                MessageSegment.text(await get_stats(user_id)),
            ],
        )
    )


@backpack.handle()
async def _backpack(bot: Bot, event: MessageEvent):
    """背包"""
    user_id = event.get_user_id()
    fmt = await get_backpack(user_id)

    if isinstance(fmt, str):
        await backpack.finish(fmt)
    else:
        messages: list[MessageSegment] = []
        # 将每个品质的信息转换为消息段
        messages.extend(MessageSegment.text(quality_info) for quality_info in fmt)
        # 创建转发消息
        forward_msg = [
            OutgoingForwardedMessage(
                name=Bot_NICKNAME,
                user_id=int(bot.self_id),
                segments=[messages_seq],
            )
            for messages_seq in messages
        ]

        await backpack.finish(MessageSegment.forward(forward_msg))


@sell.handle()
async def _sell(event: MessageEvent, arg: Message = CommandArg()):
    """卖鱼"""
    msg = arg.extract_plain_text()
    user_id = event.get_user_id()
    if msg == "":
        await sell.finish("请输入要卖出的鱼的名字，如：卖鱼 小鱼")
    if msg == "全部":
        await sell.finish(
            Message(
                [
                    MessageSegment.reply(event.data.message_seq),
                    MessageSegment.text(await sell_all_fish(user_id)),
                ],
            )
        )
    if msg in fish_quality.keys():  # 判断是否是为品质
        await sell.finish(
            Message(
                [
                    MessageSegment.reply(event.data.message_seq),
                    MessageSegment.text(await sell_quality_fish(user_id, msg)),
                ],
            )
        )
    await sell.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                MessageSegment.text(await sell_fish(user_id, msg)),
            ],
        )
    )


@balance.handle()
async def _balance(event: MessageEvent):
    """余额"""
    user_id = event.get_user_id()
    await balance.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                MessageSegment.text(await get_balance(user_id)),
            ],
        )
    )


@switch.handle()
async def _switch(event: GroupMessageEvent | FriendMessageEvent):
    """钓鱼开关"""
    if await switch_fish(event):
        await switch.finish("钓鱼 已打开")
    else:
        await switch.finish("钓鱼 已关闭")
