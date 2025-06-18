from datetime import datetime
from typing import Dict, List

from sqlalchemy import BigInteger, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from U1.database import Model


class BaseGroupModel(Model):
    __abstract__ = True

    group_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WaifuProtect(BaseGroupModel):
    __tablename__ = "waifu_protect"

    user_ids: Mapped[List[int]] = mapped_column(JSON, default=list)


class WaifuCP(BaseGroupModel):
    __tablename__ = "waifu_cp"

    affect: Mapped[Dict[str, int]] = mapped_column(JSON, default=dict)


class PWaifu(BaseGroupModel):
    __tablename__ = "waifu"

    waifu_list: Mapped[List[int]] = mapped_column(JSON, default=list)


class WaifuLock(BaseGroupModel):
    __tablename__ = "waifu_lock"

    lock: Mapped[dict] = mapped_column(JSON, default=dict)


class YinpaRecord(Model):
    __abstract__ = True

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    active_count: Mapped[int] = mapped_column(default=0)
    passive_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class YinpaActive(YinpaRecord):
    __tablename__ = "yinpa_active"


class YinpaPassive(YinpaRecord):
    __tablename__ = "yinpa_passive"
