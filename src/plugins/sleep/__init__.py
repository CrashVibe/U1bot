from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nonebot import on_fullmatch, on_startswith
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from . import scheduler
from .data_source import (
    get_all_morning_night_data,
    get_morning_msg,
    get_night_msg,
    get_weekly_sleep_data,
)

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


# 我的作息

my_sleep = on_fullmatch(msg="我的作息")


@my_sleep.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id

    user_data = await get_weekly_sleep_data(uid)

    if isinstance(user_data, str):
        await my_sleep.finish(user_data, reply_message=True)

    (
        weekly_sleep_time,
        weekly_morning_cout,
        weekly_night_cout,
        weekly_earliest_morning_time,  # datetime | str
        weekly_latest_night_time,  # datetime | str
        lastweek_sleep_time,
        lastweek_morning_cout,
        lastweek_night_cout,
        lastweek_earliest_morning_time,  # datetime | str
        lastweek_latest_night_time,  # datetime | str
    ) = user_data

    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y年%m月%d日")

    if isinstance(weekly_earliest_morning_time, datetime):
        weekly_earliest_morning_time = weekly_earliest_morning_time.strftime(
            "%Y年%m月%d日 %H:%M:%S"
        )
    if isinstance(weekly_latest_night_time, datetime):
        weekly_latest_night_time = weekly_latest_night_time.strftime(
            "%Y年%m月%d日 %H:%M:%S"
        )
    if isinstance(lastweek_earliest_morning_time, datetime):
        lastweek_earliest_morning_time = lastweek_earliest_morning_time.strftime(
            "%Y年%m月%d日 %H:%M:%S"
        )
    if isinstance(lastweek_latest_night_time, datetime):
        lastweek_latest_night_time = lastweek_latest_night_time.strftime(
            "%Y年%m月%d日 %H:%M:%S"
        )

    msg = (
        f"✨ 我的作息 ({today}) ✨\n"
        f"╔═══════════\n"
        f"║ 本周统计:\n"
        f"║  睡觉时长: {weekly_sleep_time}分钟\n"
        f"║  早安次数: {weekly_morning_cout}\n"
        f"║  晚安次数: {weekly_night_cout}\n"
        f"║  最早起床: {weekly_earliest_morning_time}\n"
        f"║  最晚睡觉: {weekly_latest_night_time}\n"
        f"╠═══════════\n"
        f"║ 上周统计:\n"
        f"║  睡觉时长: {lastweek_sleep_time}分钟\n"
        f"║  早安次数: {lastweek_morning_cout}\n"
        f"║  晚安次数: {lastweek_night_cout}\n"
        f"║  最早起床: {lastweek_earliest_morning_time}\n"
        f"║  最晚睡觉: {lastweek_latest_night_time}\n"
        f"╚═══════════"
    )

    await my_sleep.finish(msg, reply_message=True)
