from nonebot import require
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler

require("nonebot_plugin_orm")

from .config import settings
from .models import SleepGroupModel, SleepUserModel


async def group_daily_refresh() -> None:
    """
    每日早晚安刷新
    """
    from nonebot_plugin_orm import get_session
    from sqlalchemy import delete

    async with get_session() as session:
        # 重置每日早晚安
        stmt = delete(SleepGroupModel)
        await session.execute(stmt)
        await session.commit()

    logger.info("每日早晚安已刷新！")


async def user_weekly_refresh() -> None:
    """
    每周早晚安刷新, 重置每周早晚安
    """
    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    async with get_session() as session:
        # 先查询所有用户记录
        stmt = select(SleepUserModel)
        result = await session.execute(stmt)
        users = result.scalars().all()

        # 更新每个用户的记录
        for user in users:
            user.lastweek_morning_cout = user.weekly_morning_cout
            user.lastweek_sleep_time = user.weekly_sleep_time
            user.lastweek_night_cout = user.weekly_night_cout
            user.lastweek_earliest_morning_time = user.weekly_earliest_morning_time
            user.lastweek_latest_night_time = user.weekly_latest_night_time
            user.weekly_morning_cout = 0
            user.weekly_night_cout = 0
            user.weekly_sleep_time = 0
            user.weekly_earliest_morning_time = None
            user.weekly_latest_night_time = None
            session.add(user)

        await session.commit()

    logger.info("每周早晚安已刷新！")


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
