import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot_plugin_orm import get_session
from sqlalchemy import select

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


async def morning_and_update(
    uid: int, gid: int, now_time: datetime
) -> tuple[int, int, str]:
    """早安并更新数据库"""
    async with get_session() as session:
        # 获取目标用户
        stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
        result = await session.execute(stmt)
        target_user = result.scalar_one()

        # 获取所有群组
        stmt = select(SleepGroupModel)
        result = await session.execute(stmt)
        all_groups = result.scalars().all()

        # 获取或创建目标群组
        stmt = select(SleepGroupModel).where(SleepGroupModel.group_id == gid)
        result = await session.execute(stmt)
        target_group = result.scalar_one_or_none()
        if target_group is None:
            target_group = SleepGroupModel(group_id=gid)
            session.add(target_group)
            await session.flush()  # 确保对象有 ID

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
        await session.commit()

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

    async with get_session() as session:
        stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
        result = await session.execute(stmt)
        target_user = result.scalar_one_or_none()

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
    async with get_session() as session:
        # 获取或创建目标用户
        stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
        result = await session.execute(stmt)
        target_user = result.scalar_one_or_none()
        if target_user is None:
            target_user = SleepUserModel(user_id=uid)
            session.add(target_user)

        # 获取所有群组
        stmt = select(SleepGroupModel)
        result = await session.execute(stmt)
        all_groups = result.scalars().all()

        # 获取或创建目标群组
        stmt = select(SleepGroupModel).where(SleepGroupModel.group_id == gid)
        result = await session.execute(stmt)
        target_group = result.scalar_one_or_none()
        if target_group is None:
            target_group = SleepGroupModel(group_id=gid)
            session.add(target_group)

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
        await session.commit()

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

    async with get_session() as session:
        stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
        result = await session.execute(stmt)
        target_user = result.scalar_one_or_none()

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
    async with get_session() as session:
        stmt = select(SleepGroupModel)
        result = await session.execute(stmt)
        all_groups = result.scalars().all()

        morning_count = sum(group.morning_count for group in all_groups)  # 全服早安次数
        night_count = sum(group.night_count for group in all_groups)  # 全服晚安次数

        getting_up_count = morning_count
        sleeping_count = night_count - getting_up_count  # 今日睡觉人数

        # 本群数据
        stmt = select(SleepGroupModel).where(SleepGroupModel.group_id == gid)
        result = await session.execute(stmt)
        target_group = result.scalar_one_or_none()

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


async def get_weekly_sleep_data(
    uid: int,
) -> (
    tuple[
        int,
        int,
        int,
        datetime | str,
        datetime | str,
        int,
        int,
        int,
        datetime | str,
        datetime | str,
    ]
    | str
):
    """获取本周睡眠数据"""
    async with get_session() as session:
        stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
        result = await session.execute(stmt)
        target_user = result.scalar_one_or_none()

        if not target_user:
            return "没有找到你的睡眠数据呢.."
        return (
            target_user.weekly_sleep_time,
            target_user.weekly_morning_cout,
            target_user.weekly_night_cout,
            target_user.weekly_earliest_morning_time
            if target_user.weekly_earliest_morning_time
            else "无",
            target_user.weekly_latest_night_time
            if target_user.weekly_latest_night_time
            else "无",
            target_user.lastweek_sleep_time,
            target_user.lastweek_morning_cout,
            target_user.lastweek_night_cout,
            target_user.lastweek_earliest_morning_time
            if target_user.lastweek_earliest_morning_time
            else "无",
            target_user.lastweek_latest_night_time
            if target_user.lastweek_latest_night_time
            else "无",
        )
