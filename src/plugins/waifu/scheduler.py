from nonebot_plugin_apscheduler import scheduler

from .main import clean_cd_cache, reset_record


def setup_scheduler():
    scheduler.add_job(
        reset_record, "cron", hour=0, minute=0, misfire_grace_time=300, coalesce=True
    )

    scheduler.add_job(clean_cd_cache, "interval", hours=1, coalesce=True)
