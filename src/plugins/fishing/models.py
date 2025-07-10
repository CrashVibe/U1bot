from nonebot import require

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm.properties import MappedColumn


class FishingRecord(Model):
    __tablename__ = "fishing_fishingrecord"

    id: MappedColumn[int] = mapped_column(Integer, primary_key=True)
    user_id: MappedColumn[str] = mapped_column(String(32))
    time: MappedColumn[int] = mapped_column(Integer)
    frequency: MappedColumn[int] = mapped_column(Integer)
    fishes: MappedColumn[str] = mapped_column(Text)


class FishingSwitch(Model):
    __tablename__ = "fishing_fishingswitch"

    group_id: MappedColumn[int] = mapped_column(Integer, primary_key=True)
    switch: MappedColumn[bool] = mapped_column(Boolean, default=True)
