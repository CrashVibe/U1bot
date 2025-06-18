# 导入插件方法
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from U1.database import Model


class MemberData(Model):
    __tablename__ = "today_yunshi_memberdata"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    luckid: Mapped[int] = mapped_column(Integer, default=0)
    time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
