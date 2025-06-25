from nonebot import require
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

require("nonebot_plugin_orm")

from .config import settings
from .models import SleepGroupModel, SleepUserModel


async def group_daily_refresh() -> None:
    """每日早晚安刷新 - 优化版本"""
    from nonebot_plugin_orm import get_session
    from sqlalchemy import delete

    async with get_session() as session:
        # 使用批量删除，比逐个删除更高效
        stmt = delete(SleepGroupModel)
        result = await session.execute(stmt)
        await session.commit()

        deleted_count = result.rowcount
        logger.info(f"每日早晚安已刷新！删除了 {deleted_count} 个群组记录")


async def user_weekly_refresh() -> None:
    """每周早晚安刷新 - 优化版本"""
    from nonebot_plugin_orm import get_session
    from sqlalchemy import update

    async with get_session() as session:
        # 使用批量更新而不是逐个更新，提高性能
        stmt = update(SleepUserModel).values(
            # 将本周数据移到上周
            lastweek_morning_cout=SleepUserModel.weekly_morning_cout,
            lastweek_sleep_time=SleepUserModel.weekly_sleep_time,
            lastweek_night_cout=SleepUserModel.weekly_night_cout,
            lastweek_earliest_morning_time=SleepUserModel.weekly_earliest_morning_time,
            lastweek_latest_night_time=SleepUserModel.weekly_latest_night_time,
            # 重置本周数据
            weekly_morning_cout=0,
            weekly_night_cout=0,
            weekly_sleep_time=0,
            weekly_earliest_morning_time=None,
            weekly_latest_night_time=None,
        )

        result = await session.execute(stmt)
        await session.commit()

        updated_count = result.rowcount
        logger.info(f"每周早晚安已刷新！更新了 {updated_count} 个用户记录")


# 条件性添加定时任务
if settings.night_night_intime_enable:
    scheduler.add_job(
        group_daily_refresh,
        "cron",
        id="daily_scheduler",
        replace_existing=True,
        hour=settings.night_night_intime_early_time,
        minute=0,
        misfire_grace_time=None,
    )

# 每周一凌晨刷新
scheduler.add_job(
    user_weekly_refresh,
    "cron",
    id="weekly_scheduler",
    replace_existing=True,
    day_of_week=1,
    hour=0,
    minute=0,
    misfire_grace_time=None,
)
