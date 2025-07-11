from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import on_fullmatch, on_startswith
from nonebot.adapters import Bot
from nonebot.adapters.milky import Message, MessageSegment
from nonebot.adapters.milky.event import GroupMessageEvent

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
    uid = event.data.sender_id
    gid = event.data.peer_id

    await morning.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                await get_morning_msg(uid, gid),
            ],
        )
    )


@night.handle()
@night_2.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    uid = event.data.sender_id
    gid = event.data.peer_id

    await night.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                await get_night_msg(uid, gid),
            ],
        )
    )


# 早晚安大统计

statistics = on_fullmatch(msg="早晚安统计")


@statistics.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    gid = event.data.peer_id

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

    await statistics.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                MessageSegment.text(msg),
            ],
        )
    )


# 我的作息

my_sleep = on_fullmatch(msg="我的作息")


@my_sleep.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    uid = event.data.sender_id

    user_data = await get_weekly_sleep_data(uid)

    if user_data is None:
        await my_sleep.finish(
            Message(
                [
                    MessageSegment.reply(event.data.message_seq),
                    MessageSegment.text("未找到你的作息数据呢......"),
                ],
            )
        )

    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y年%m月%d日")

    # 格式化时间显示
    def format_time(dt: datetime | None) -> str:
        return "无" if dt is None else dt.strftime("%Y年%m月%d日 %H:%M:%S")

    # 格式化睡眠时长（从秒转换为小时分钟）
    def format_sleep_time(seconds: int) -> str:
        if seconds == 0:
            return "0小时"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0 and minutes > 0:
            return f"{hours}小时{minutes}分钟"
        elif hours > 0:
            return f"{hours}小时"
        else:
            return f"{minutes}分钟"

    msg = (
        f"✨ 我的作息 ({today}) ✨\n"
        f"╔═══════════\n"
        f"║ 本周统计:\n"
        f"║  睡觉时长: {format_sleep_time(user_data.weekly_sleep_time)}\n"
        f"║  平均睡眠: {user_data.weekly_avg_sleep_hours:.1f}小时/天\n"
        f"║  早安次数: {user_data.weekly_morning_count}\n"
        f"║  晚安次数: {user_data.weekly_night_count}\n"
        f"║  最早起床: {format_time(user_data.weekly_earliest_morning)}\n"
        f"║  最晚睡觉: {format_time(user_data.weekly_latest_night)}\n"
        f"╠═══════════\n"
        f"║ 上周统计:\n"
        f"║  睡觉时长: {format_sleep_time(user_data.lastweek_sleep_time)}\n"
        f"║  平均睡眠: {user_data.lastweek_avg_sleep_hours:.1f}小时/天\n"
        f"║  早安次数: {user_data.lastweek_morning_count}\n"
        f"║  晚安次数: {user_data.lastweek_night_count}\n"
        f"║  最早起床: {format_time(user_data.lastweek_earliest_morning)}\n"
        f"║  最晚睡觉: {format_time(user_data.lastweek_latest_night)}\n"
        f"╚═══════════"
    )

    await my_sleep.finish(
        Message(
            [
                MessageSegment.reply(event.data.message_seq),
                MessageSegment.text(msg),
            ],
        )
    )
