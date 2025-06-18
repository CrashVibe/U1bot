from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from U1.database import Model


class FishingRecord(Model):
    __tablename__ = "fishing_fishingrecord"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text)
    time: Mapped[int] = mapped_column(Integer)
    frequency: Mapped[int] = mapped_column(Integer)
    fishes: Mapped[str] = mapped_column(Text)
    coin: Mapped[float] = mapped_column(Float, default=0)
    count_coin: Mapped[float] = mapped_column(Float, default=0)


class FishingSwitch(Model):
    __tablename__ = "fishing_fishingswitch"

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    switch: Mapped[bool] = mapped_column(Boolean, default=True)
