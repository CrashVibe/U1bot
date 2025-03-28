import asyncio
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nonebot.adapters.onebot.v11 import MessageSegment

from .config import settings
from .models import SleepGroupModel, SleepUserModel
from .utils import (
    check_morning_time_in_range,
    check_night_time_in_range,
    get_adjusted_minutes,
    isTimeInMorningRange,
    isTimeInNightRange,
    morning_prompt,
    night_prompt,
    total_seconds2tuple_time,
)


async def morning_and_update(
    uid: int, gid: int, now_time: datetime
) -> tuple[int, int, str]:
    """早安并更新数据库"""
    target_user_task = SleepUserModel.get(user_id=uid)
    all_groups_task = SleepGroupModel.all()
    target_group_task = SleepGroupModel.get_or_create(group_id=gid)
    target_user, (target_group, _) = await asyncio.gather(
        target_user_task, target_group_task
    )
    if target_user.night_time is None:
        raise ValueError("用户没有晚安记录哦")
    sleep_time = now_time - target_user.night_time

    _, hours, minutes, seconds = total_seconds2tuple_time(
        int(sleep_time.total_seconds())
    )

    in_sleep_tmp = f"{hours}小时{minutes}分钟{seconds}秒"
    target_user.weekly_sleep_time += int(sleep_time.total_seconds())
    target_user.total_sleep_time += int(sleep_time.total_seconds())

    target_user.morning_time = now_time
    target_user.weekly_morning_cout += 1
    target_user.morning_count += 1

    week_emt = target_user.weekly_earliest_morning_time
    if week_emt is None:
        target_user.weekly_earliest_morning_time = now_time
    elif now_time.time() < week_emt.time():
        target_user.weekly_earliest_morning_time = now_time

    # 判断今天第几个起床
    target_group.morning_count += 1
    await target_group.save()
    await target_user.save()

    all_groups = await all_groups_task
    server_morning_count = sum(group.morning_count for group in all_groups)
    server_rank = server_morning_count

    return target_group.morning_count, server_rank, in_sleep_tmp


async def get_morning_msg(uid: int, gid: int) -> MessageSegment:
    """获取早安消息"""
    now_time = datetime.now(ZoneInfo("Asia/Shanghai"))
    if settings.morning_morning_intime_enable:
        early_time: int = settings.morning_morning_intime_early_time
        late_time: int = settings.morning_morning_intime_late_time
        if not isTimeInMorningRange(early_time, late_time, now_time):
            msg = f"现在都 {now_time.hour} 点啦(╯‵□′)╯︵┻━┻ 这个点不能起床哦~"
            return MessageSegment.text(msg)

    target_user = await SleepUserModel.get_or_none(user_id=uid)

    if target_user and target_user.night_time:  # 用户存在
        # 判断是否隔日
        last_sleep_time = target_user.night_time
        if last_sleep_time - now_time < timedelta(days=1):  # 没有隔日
            # 是否是可以持续多次早安
            if not settings.morning_mult_get_up_enable:
                if (
                    target_user.morning_time
                    and now_time - target_user.morning_time
                    < timedelta(hours=settings.morning_mult_get_up_interval)
                ):
                    msg = f"(｀へ′) {settings.morning_mult_get_up_interval} 小时内已经早安过啦~"
                    return MessageSegment.text(msg)

            if not settings.morning_super_get_up_enable:
                if now_time - target_user.night_time < timedelta(
                    hours=settings.morning_super_get_up_interval
                ):
                    msg = "睡这么点没关系吗？要不再睡一会吧... /_ \\"
                    return MessageSegment.text(msg)
        else:  # 隔日
            msg = f"{random.choice(morning_prompt)}"
            return MessageSegment.text(msg)
    else:  # 用户不存在，意味着没有晚安
        msg = f"{random.choice(morning_prompt)}"
        return MessageSegment.text(msg)

    num, server_rank, in_sleep_tmp = await morning_and_update(uid, gid, now_time)
    return MessageSegment.text(
        f"你是第 {server_rank} 个起床哒，群里第 {num} 个\n睡了 {in_sleep_tmp}，{random.choice(morning_prompt)}"
    )


async def night_and_update(
    uid: int, gid: int, now_time: datetime
) -> tuple[int, int, str | None]:
    """晚安并更新数据库"""
    target_user_task = SleepUserModel.get_or_create(user_id=uid)
    all_groups_task = SleepGroupModel.all()
    target_group_task = SleepGroupModel.get_or_create(group_id=gid)
    (target_user, _), (target_group, _) = await asyncio.gather(
        target_user_task, target_group_task
    )
    target_user.night_time = now_time
    target_user.night_count += 1
    target_user.weekly_night_cout += 1
    if week_emt := target_user.weekly_latest_night_time:
        # 获取调整后的分钟数进行比较
        now_adjusted, _ = get_adjusted_minutes(now_time.time())
        last_adjusted, _ = get_adjusted_minutes(week_emt.time())

        if now_adjusted > last_adjusted:
            target_user.weekly_latest_night_time = now_time
    else:
        target_user.weekly_latest_night_time = now_time

    in_day_tmp: None | str = None
    if target_user.morning_time:
        in_day = now_time - target_user.morning_time
        _, hours, minutes, seconds = total_seconds2tuple_time(
            int(in_day.total_seconds())
        )
        if in_day.days == 0:
            in_day_tmp = f"{hours}小时{minutes}分钟{seconds}秒"

    target_group.night_count += 1
    await target_user.save()
    await target_group.save()

    all_groups = await all_groups_task
    server_night_count = sum(group.night_count for group in all_groups)
    server_rank = server_night_count

    return target_group.night_count, server_rank, in_day_tmp


async def get_night_msg(uid: int, gid: int) -> MessageSegment:
    """获取晚安消息"""
    now_time = datetime.now(ZoneInfo("Asia/Shanghai"))

    # 若开启规定时间晚安，则判断该时间是否允许晚安
    if settings.night_night_intime_enable:
        early_time: int = settings.night_night_intime_early_time
        late_time: int = settings.night_night_intime_late_time
        if not isTimeInNightRange(early_time, late_time, now_time):
            msg = f"拜托现在才 {now_time.hour} 点了！才不是睡觉时间啦！=n="
            return MessageSegment.text(msg)

    target_user = await SleepUserModel.get_or_none(user_id=uid)

    if target_user and target_user.night_time:  # 用户存在
        if settings.night_good_sleep_enable:
            if now_time - target_user.night_time < timedelta(
                hours=settings.night_good_sleep_interval
            ):
                msg = f"(｀へ′)  {settings.night_good_sleep_interval} 小时内你已经晚安过啦~"
                return MessageSegment.text(msg)

        if not settings.night_deep_sleep_enable:
            if (
                target_user.morning_time
                and now_time - target_user.morning_time
                < timedelta(hours=settings.night_deep_sleep_interval)
            ):
                msg = "这是要睡回笼觉吗？要不再玩一会吧... /_ \\"
                return MessageSegment.text(msg)

    num, server_rank, in_day = await night_and_update(uid, gid, now_time)
    if in_day:
        return MessageSegment.text(
            f"你是第 {server_rank} 个睡觉哒，群里第 {num} 个\n活动了 {in_day}，{random.choice(night_prompt)}"
        )
    else:
        return MessageSegment.text(
            f"你是第 {server_rank} 个睡觉哒，群里第 {num} 个\n{random.choice(night_prompt)}"
        )


# 全服今日早晚安各个数据统计，要各种百分比统计
async def get_all_morning_night_data(
    gid: int,
) -> tuple[int, int, int, int, float, float, int, int]:
    """全服早晚安数据统计

    Args:
        gid: 群号

    Returns:
        morning_count: 全服早安次数
        night_count: 全服晚安次数
        sleeping_count: 今日睡觉人数
        get_up_cout: 今日起床人数
        morning_percent: 本群在全服的早安占比
        night_percent: 本群在全服的晚安占比
        group_morning_count: 本群早安次数
        group_night_count: 本群晚安次数
    """
    all_groups = await SleepGroupModel.all()
    morning_count = sum(group.morning_count for group in all_groups)  # 全服早安次数
    night_count = sum(group.night_count for group in all_groups)  # 全服晚安次数

    all_users = await SleepUserModel.all()
    sleeping_count = 0
    getting_up_count = 0
    now_time = datetime.now(ZoneInfo("Asia/Shanghai"))
    # 输出下面条件判断的所有判断
    for user in all_users:
        is_night_time = user.night_time and check_night_time_in_range(
            user.night_time, now_time
        )
        is_morning_time = user.morning_time and check_morning_time_in_range(
            user.morning_time, now_time
        )

        if is_night_time:
            if not is_morning_time:
                sleeping_count += 1

        if is_morning_time:
            getting_up_count += 1

    # 本群数据
    target_group = await SleepGroupModel.get_or_none(group_id=gid)
    group_morning_count = target_group.morning_count if target_group else 0
    group_night_count = target_group.night_count if target_group else 0

    # 全服占比
    morning_percent = group_morning_count / morning_count if morning_count else 0
    night_percent = group_night_count / night_count if night_count else 0
    return (
        morning_count,
        night_count,
        sleeping_count,
        getting_up_count,
        morning_percent,
        night_percent,
        group_morning_count,
        group_night_count,
    )
