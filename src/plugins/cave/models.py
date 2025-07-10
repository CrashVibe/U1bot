# 导入插件方法
from datetime import datetime

from nonebot import require

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model
from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm.properties import MappedColumn


class cave_models(Model):
    __tablename__ = "cave_models"

    id: MappedColumn[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    details: MappedColumn[str] = mapped_column(LONGTEXT)
    img_base64: MappedColumn[list[str]] = mapped_column(JSON, default=[])
    user_id: MappedColumn[int] = mapped_column(BigInteger)
    time: MappedColumn[datetime] = mapped_column(DateTime, default=datetime.now)
    anonymous: MappedColumn[bool] = mapped_column(Boolean, default=False)
