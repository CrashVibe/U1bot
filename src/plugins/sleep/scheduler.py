from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import delete as sa_delete, update as sa_update

from U1.database import get_scoped_session

from .config import settings
from .models import SleepGroupModel, SleepUserModel


async def group_daily_refresh() -> None:
    """
    每日早晚安刷新
    """

    # 重置每日早晚安
    session = get_scoped_session()
    await session.execute(sa_delete(SleepGroupModel))
    await session.commit()

    logger.info("每日早晚安已刷新！")


async def user_weekly_refresh() -> None:
    """
    每周早晚安刷新, 重置每周早晚安
    """

    session = get_scoped_session()
    await session.execute(
        sa_update(SleepUserModel)
        .values(
            lastweek_morning_cout=SleepUserModel.weekly_morning_cout,
            lastweek_sleep_time=SleepUserModel.weekly_sleep_time,
            lastweek_night_cout=SleepUserModel.weekly_night_cout,
            lastweek_earliest_morning_time=SleepUserModel.weekly_earliest_morning_time,
            lastweek_latest_night_time=SleepUserModel.weekly_latest_night_time,
            weekly_morning_cout=0,
            weekly_night_cout=0,
            weekly_sleep_time=0,
            weekly_earliest_morning_time=None,
            weekly_latest_night_time=None,
        )
    )
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
