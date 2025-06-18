# 导入插件方法
from datetime import datetime

from nonebot import require

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model
from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column


class MemberData(Model):
    __tablename__ = "today_yunshi_memberdata"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    luckid: Mapped[int] = mapped_column(Integer, default=0)
    time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )
