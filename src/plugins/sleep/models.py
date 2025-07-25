from datetime import datetime

from nonebot import require

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

class SleepGroupModel(Model):
    __tablename__ = "sleep_group"

    group_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # 每日早晚安
    morning_count: Mapped[int] = mapped_column(Integer, default=0)
    night_count: Mapped[int] = mapped_column(Integer, default=0)


class SleepUserModel(Model):
    __tablename__ = "sleep_user"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    # 每日早晚安
    night_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    morning_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 每周早晚安
    weekly_morning_cout: Mapped[int] = mapped_column(Integer, default=0)  # 早安次数
    weekly_night_cout: Mapped[int] = mapped_column(Integer, default=0)  # 晚安次数
    weekly_sleep_time: Mapped[int] = mapped_column(Integer, default=0)  # 睡觉时间
    weekly_earliest_morning_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )  # 最早起床时间
    weekly_latest_night_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )  # 最晚睡觉时间

    # 这周迁移到上周
    lastweek_morning_cout: Mapped[int] = mapped_column(Integer, default=0)
    lastweek_night_cout: Mapped[int] = mapped_column(Integer, default=0)
    lastweek_sleep_time: Mapped[int] = mapped_column(Integer, default=0)
    lastweek_earliest_morning_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    lastweek_latest_night_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # 总数
    morning_count: Mapped[int] = mapped_column(Integer, default=0)
    night_count: Mapped[int] = mapped_column(Integer, default=0)
    total_sleep_time: Mapped[int] = mapped_column(Integer, default=0)
