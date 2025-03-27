import asyncio
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nonebot.adapters.onebot.v11 import MessageSegment

from .config import settings
from .models import SleepGroupModel, SleepUserModel
from .utils import (
    get_adjusted_minutes,
    isTimeInMorningRange,
    isTimeInNightRange,
    morning_prompt,
    night_prompt,
    total_seconds2tuple_time,
)


async def morning_and_update(uid: int, gid: int, now_time: datetime) -> tuple[int, str]:
    """早安并更新数据库"""
    target_user_task = SleepUserModel.get(user_id=uid)
    target_group_task = SleepGroupModel.get_or_create(group_id=gid)
    target_user, (target_group, _) = await asyncio.gather(
        target_user_task, target_group_task
    )
    if target_user.night_time is None:
        raise ValueError("用户没有晚安记录")
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

    return target_group.morning_count, in_sleep_tmp


async def get_morning_msg(uid: int, gid: int) -> MessageSegment:
    """获取早安消息"""
    now_time = datetime.now(ZoneInfo("Asia/Shanghai"))
    if settings.morning_morning_intime_enable:
        early_time: int = settings.morning_morning_intime_early_time
        late_time: int = settings.morning_morning_intime_late_time
        if not isTimeInMorningRange(early_time, late_time, now_time):
            msg = f"现在是{now_time.hour}点了，你不能起床~"
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
                    msg = f"{settings.morning_mult_get_up_interval}今天已经早安过了哦~"
                    return MessageSegment.text(msg)

            if not settings.morning_super_get_up_enable:
                if now_time - target_user.night_time < timedelta(
                    hours=settings.morning_super_get_up_interval
                ):
                    msg = "不是哥们，你刚刚睡着了吗？"
                    return MessageSegment.text(msg)
        else:  # 隔日
            msg = f"{random.choice(morning_prompt)}哎呀，你昨天没有早安呢~"
            return MessageSegment.text(msg)
    else:  # 用户不存在，意味着没有晚安
        msg = f"{random.choice(morning_prompt)}哎呀，你还没有早安呢~"
        return MessageSegment.text(msg)

    num, in_sleep_tmp = await morning_and_update(uid, gid, now_time)
    return MessageSegment.text(
        f"{random.choice(morning_prompt)}你是群里第 {num} 起床的~\n你昨晚睡了{in_sleep_tmp}"
    )


async def night_and_update(
    uid: int, gid: int, now_time: datetime
) -> tuple[int, str | None]:
    """晚安并更新数据库"""
    target_user_task = SleepUserModel.get_or_create(user_id=uid)
    target_group_task = SleepGroupModel.get_or_create(group_id=gid)
    (target_user, _), (target_group, _) = await asyncio.gather(
        target_user_task, target_group_task
    )
    target_user.night_time = now_time
    target_user.night_count += 1
    target_user.weekly_night_cout += 1
    if week_emt := target_user.weekly_latest_night_time:
        # 获取调整后的分钟数进行比较
        now_adjusted = get_adjusted_minutes(now_time.time())
        last_adjusted = get_adjusted_minutes(week_emt.time())

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
    return target_group.night_count, in_day_tmp


async def get_night_msg(uid: int, gid: int) -> MessageSegment:
    """获取晚安消息"""
    now_time = datetime.now(ZoneInfo("Asia/Shanghai"))

    # 若开启规定时间晚安，则判断该时间是否允许晚安
    if settings.night_night_intime_enable:
        early_time: int = settings.night_night_intime_early_time
        late_time: int = settings.night_night_intime_late_time
        if not isTimeInNightRange(early_time, late_time, now_time):
            msg = f"现在是{now_time.hour}点了，不是睡觉时间！"
            return MessageSegment.text(msg)

    target_user = await SleepUserModel.get_or_none(user_id=uid)

    if target_user and target_user.night_time:  # 用户存在
        if settings.night_good_sleep_enable:
            if now_time - target_user.night_time < timedelta(
                hours=settings.night_good_sleep_interval
            ):
                msg = f"{settings.night_good_sleep_interval}小时内你已经晚安过了哦~"
                return MessageSegment.text(msg)

        if not settings.night_deep_sleep_enable:
            if (
                target_user.morning_time
                and now_time - target_user.morning_time
                < timedelta(hours=settings.night_deep_sleep_interval)
            ):
                msg = "你刚刚起床了吧？真的要睡了吗？不好吧"
                return MessageSegment.text(msg)

    num, in_day = await night_and_update(uid, gid, now_time)
    if in_day:
        return MessageSegment.text(
            f"你是群里第{num}个睡觉的，你在白天待了{in_day}，{random.choice(night_prompt)}"
        )
    else:
        return MessageSegment.text(
            f"你是群里第{num}个睡觉的，{random.choice(night_prompt)}"
        )
