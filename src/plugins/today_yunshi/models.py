from datetime import datetime

from nonebot import require
from sqlalchemy.orm.properties import MappedColumn

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model
from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import mapped_column


class MemberData(Model):
    __tablename__ = "today_yunshi_memberdata"

    user_id: MappedColumn[int] = mapped_column(BigInteger, primary_key=True)
    luckid: MappedColumn[int] = mapped_column(Integer, default=0)
    time: MappedColumn[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
