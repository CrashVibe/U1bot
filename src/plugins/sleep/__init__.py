from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import on_fullmatch, on_startswith
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from . import scheduler
from .data_source import get_all_morning_night_data, get_morning_msg, get_night_msg

__all__ = ["scheduler"]

morning = on_startswith(
    msg=(
        "早安",
        "早哇",
        "起床",
        "早上好",
        "ohayo",
        "哦哈哟",
        "お早う",
        "good morning",
    )
)
morning_2 = on_fullmatch(msg="早")

night = on_startswith(
    msg=(
        "晚安",
        "晚好",
        "睡觉",
        "晚上好",
        "oyasuminasai",
        "おやすみなさい",
        "good evening",
        "good night",
    )
)

night_2 = on_fullmatch(msg="晚")


@morning.handle()
@morning_2.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id
    gid = event.group_id

    await morning.finish(await get_morning_msg(uid, gid), reply_message=True)


@night.handle()
@night_2.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id
    gid = event.group_id

    await night.finish(await get_night_msg(uid, gid), reply_message=True)


# 早晚安大统计

statistics = on_fullmatch(msg="早晚安统计")


@statistics.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    gid = event.group_id
    (
        morning_count,
        night_count,
        sleeping_count,
        get_up_cout,
        morning_percent,
        night_percent,
        group_morning_count,
        group_night_count,
    ) = await get_all_morning_night_data(gid)

    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y年%m月%d日")

    msg = (
        f"✨ 今日睡眠统计 ({today}) ✨\n"
        f"╔═══════════\n"
        f"║ 全服统计:\n"
        f"║  早安次数: {morning_count:>6}\n"
        f"║  晚安次数: {night_count:>6}\n"
        f"║  正在睡觉: {sleeping_count:>6}\n"
        f"║  已经起床: {get_up_cout:>6}\n"
        f"╠═══════════\n"
        f"║ 本群统计:\n"
        f"║  早安次数: {group_morning_count:>6}\n"
        f"║  晚安次数: {group_night_count:>6}\n"
        f"║  早安占比: {morning_percent:>6.2%}\n"
        f"║  晚安占比: {night_percent:>6.2%}\n"
        f"╚═══════════"
    )

    await statistics.finish(msg, reply_message=True)
