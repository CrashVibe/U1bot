import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot_plugin_orm import get_session
from sqlalchemy import func, select

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


@dataclass
class WeeklySleepData:
    """用户周睡眠数据结构"""

    # 本周数据
    weekly_sleep_time: int = 0
    weekly_morning_count: int = 0
    weekly_night_count: int = 0
    weekly_earliest_morning: datetime | None = None
    weekly_latest_night: datetime | None = None

    # 上周数据
    lastweek_sleep_time: int = 0
    lastweek_morning_count: int = 0
    lastweek_night_count: int = 0
    lastweek_earliest_morning: datetime | None = None
    lastweek_latest_night: datetime | None = None

    @property
    def weekly_avg_sleep_hours(self) -> float:
        """本周平均睡眠小时数"""
        return self.weekly_sleep_time / 3600 / max(self.weekly_night_count, 1)

    @property
    def lastweek_avg_sleep_hours(self) -> float:
        """上周平均睡眠小时数"""
        return self.lastweek_sleep_time / 3600 / max(self.lastweek_night_count, 1)


def ensure_timezone_aware(dt: datetime) -> datetime:
    """确保 datetime 对象具有时区信息，如果没有则添加 Asia/Shanghai 时区"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return dt


async def get_or_create_user(session, uid: int) -> SleepUserModel:
    """获取或创建用户记录"""
    stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
    result = await session.execute(stmt)
    target_user = result.scalar_one_or_none()
    if target_user is None:
        target_user = SleepUserModel(user_id=uid)
        session.add(target_user)
        await session.flush()
    return target_user


async def get_or_create_group(session, gid: int) -> SleepGroupModel:
    """获取或创建群组记录"""
    stmt = select(SleepGroupModel).where(SleepGroupModel.group_id == gid)
    result = await session.execute(stmt)
    target_group = result.scalar_one_or_none()
    if target_group is None:
        target_group = SleepGroupModel(group_id=gid, night_count=0, morning_count=0)
        session.add(target_group)
        await session.flush()
    return target_group


async def get_server_stats(session) -> tuple[int, int]:
    """获取服务器统计数据"""
    # 使用聚合函数代替获取所有记录
    morning_stmt = select(func.coalesce(func.sum(SleepGroupModel.morning_count), 0))
    night_stmt = select(func.coalesce(func.sum(SleepGroupModel.night_count), 0))

    morning_result = await session.execute(morning_stmt)
    night_result = await session.execute(night_stmt)

    total_morning = morning_result.scalar()
    total_night = night_result.scalar()

    return total_morning, total_night


def calculate_sleep_duration(sleep_time: timedelta) -> str:
    """计算睡眠时长格式化字符串"""
    _, hours, minutes, seconds = total_seconds2tuple_time(
        int(sleep_time.total_seconds())
    )
    return f"{hours}小时{minutes}分钟{seconds}秒"


def is_within_time_range(last_time: datetime, now_time: datetime, hours: int) -> bool:
    """检查两个时间是否在指定小时数范围内"""
    return now_time - last_time < timedelta(hours=hours)


async def morning_and_update(
    uid: int, gid: int, now_time: datetime
) -> tuple[int, int, str]:
    """早安并更新数据库"""
    async with get_session() as session:
        # 获取目标用户
        stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
        result = await session.execute(stmt)
        target_user = result.scalar_one()

        if target_user.night_time is None:
            raise ValueError("用户没有晚安记录哦")

        # 获取或创建目标群组
        target_group = await get_or_create_group(session, gid)

        # 计算睡眠时长
        night_time = ensure_timezone_aware(target_user.night_time)
        sleep_time = now_time - night_time
        sleep_duration_str = calculate_sleep_duration(sleep_time)
        sleep_seconds = int(sleep_time.total_seconds())

        # 更新用户数据
        target_user.morning_time = now_time
        target_user.weekly_morning_cout += 1
        target_user.morning_count += 1
        target_user.weekly_sleep_time += sleep_seconds
        target_user.total_sleep_time += sleep_seconds

        # 更新最早起床时间
        week_emt = target_user.weekly_earliest_morning_time
        if week_emt is None or now_time.time() < week_emt.time():
            target_user.weekly_earliest_morning_time = now_time

        # 安全检查并更新群组早安次数
        if target_group.morning_count is None:
            target_group.morning_count = 0
        target_group.morning_count += 1

        # 获取服务器统计数据（优化：使用聚合查询）
        total_morning, _ = await get_server_stats(session)
        server_rank = total_morning + 1  # 当前用户是第几个早安的

        # 获取当前群组早安次数
        current_group_morning_count = target_group.morning_count

        await session.commit()

        return current_group_morning_count, server_rank, sleep_duration_str


async def get_morning_msg(uid: int, gid: int) -> MessageSegment:
    """获取早安消息"""
    now_time = datetime.now(ZoneInfo("Asia/Shanghai"))

    # 检查早安时间限制
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

        # 用户不存在或没有晚安记录
        if not target_user or not target_user.night_time:
            return MessageSegment.text(f"{random.choice(morning_prompt)}")

        last_sleep_time = ensure_timezone_aware(target_user.night_time)

        # 检查是否隔日
        if now_time - last_sleep_time >= timedelta(days=1):
            return MessageSegment.text(f"{random.choice(morning_prompt)}")

        # 检查多次早安限制
        if not settings.morning_mult_get_up_enable and target_user.morning_time:
            last_morning_time = ensure_timezone_aware(target_user.morning_time)
            if is_within_time_range(
                last_morning_time, now_time, settings.morning_mult_get_up_interval
            ):
                msg = f"(｀へ′) {settings.morning_mult_get_up_interval} 小时内已经早安过啦~"
                return MessageSegment.text(msg)

        # 检查超级早起限制
        if not settings.morning_super_get_up_enable:
            if is_within_time_range(
                last_sleep_time, now_time, settings.morning_super_get_up_interval
            ):
                return MessageSegment.text("睡这么点没关系吗？要不再睡一会吧... /_ \\")

    # 执行早安更新
    num, server_rank, sleep_duration = await morning_and_update(uid, gid, now_time)
    return MessageSegment.text(
        f"你是第 {server_rank} 个起床哒，群里第 {num} 个\n睡了 {sleep_duration}，{random.choice(morning_prompt)}"
    )


async def night_and_update(
    uid: int, gid: int, now_time: datetime
) -> tuple[int, int, str | None]:
    """晚安并更新数据库"""
    async with get_session() as session:
        # 获取或创建目标用户和群组
        target_user = await get_or_create_user(session, uid)
        target_group = await get_or_create_group(session, gid)

        # 更新用户晚安数据
        target_user.night_time = now_time
        target_user.night_count += 1
        target_user.weekly_night_cout += 1

        # 更新最晚睡觉时间
        week_emt = target_user.weekly_latest_night_time
        if week_emt:
            now_adjusted, _ = get_adjusted_minutes(now_time.time())
            last_adjusted, _ = get_adjusted_minutes(week_emt.time())
            if now_adjusted > last_adjusted:
                target_user.weekly_latest_night_time = now_time
        else:
            target_user.weekly_latest_night_time = now_time

        # 计算今日活动时间
        in_day_tmp: str | None = None
        if target_user.morning_time:
            morning_time = ensure_timezone_aware(target_user.morning_time)
            in_day = now_time - morning_time
            if in_day.days == 0:
                in_day_tmp = calculate_sleep_duration(in_day)

        # 安全检查并更新群组晚安次数
        if target_group.night_count is None:
            target_group.night_count = 0
        target_group.night_count += 1

        # 获取服务器统计数据（优化：使用聚合查询）
        _, total_night = await get_server_stats(session)
        server_rank = total_night + 1  # 当前用户是第几个晚安的

        # 获取当前群组晚安次数
        current_group_night_count = target_group.night_count

        await session.commit()

        return current_group_night_count, server_rank, in_day_tmp


async def get_night_msg(uid: int, gid: int) -> MessageSegment:
    """获取晚安消息"""
    now_time = datetime.now(ZoneInfo("Asia/Shanghai"))

    # 检查晚安时间限制
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

        if target_user:
            # 检查晚安间隔限制
            if settings.night_good_sleep_enable and target_user.night_time:
                night_time = ensure_timezone_aware(target_user.night_time)
                if is_within_time_range(
                    night_time, now_time, settings.night_good_sleep_interval
                ):
                    msg = f"(｀へ′)  {settings.night_good_sleep_interval} 小时内你已经晚安过啦~"
                    return MessageSegment.text(msg)

            # 检查深度睡眠限制
            if not settings.night_deep_sleep_enable and target_user.morning_time:
                morning_time = ensure_timezone_aware(target_user.morning_time)
                if is_within_time_range(
                    morning_time, now_time, settings.night_deep_sleep_interval
                ):
                    return MessageSegment.text(
                        "这是要睡回笼觉吗？要不再玩一会吧... /_ \\"
                    )

    # 执行晚安更新
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
        # 使用优化的聚合查询获取服务器统计
        morning_count, night_count = await get_server_stats(session)

        getting_up_count = morning_count
        sleeping_count = night_count - getting_up_count  # 今日睡觉人数

        # 获取本群数据
        stmt = select(SleepGroupModel).where(SleepGroupModel.group_id == gid)
        result = await session.execute(stmt)
        target_group = result.scalar_one_or_none()

        group_morning_count = (target_group.morning_count or 0) if target_group else 0
        group_night_count = (target_group.night_count or 0) if target_group else 0

        # 计算全服占比
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


async def get_weekly_sleep_data(uid: int) -> WeeklySleepData | None:
    """获取本周睡眠数据 - 优化版本

    Args:
        uid: 用户ID

    Returns:
        WeeklySleepData对象或None（如果用户不存在）
    """
    async with get_session() as session:
        stmt = select(SleepUserModel).where(SleepUserModel.user_id == uid)
        result = await session.execute(stmt)
        target_user = result.scalar_one_or_none()

        if not target_user:
            return None

        return WeeklySleepData(
            weekly_sleep_time=target_user.weekly_sleep_time or 0,
            weekly_morning_count=target_user.weekly_morning_cout or 0,
            weekly_night_count=target_user.weekly_night_cout or 0,
            weekly_earliest_morning=target_user.weekly_earliest_morning_time,
            weekly_latest_night=target_user.weekly_latest_night_time,
            lastweek_sleep_time=target_user.lastweek_sleep_time or 0,
            lastweek_morning_count=target_user.lastweek_morning_cout or 0,
            lastweek_night_count=target_user.lastweek_night_cout or 0,
            lastweek_earliest_morning=target_user.lastweek_earliest_morning_time,
            lastweek_latest_night=target_user.lastweek_latest_night_time,
        )
