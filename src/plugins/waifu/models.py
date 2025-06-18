from datetime import datetime

from nonebot import require

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model
from sqlalchemy import JSON, BigInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column


class BaseGroupModel(Model):
    __abstract__ = True

    group_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WaifuProtect(BaseGroupModel):
    __tablename__ = "waifu_protect"

    user_ids: Mapped[list[int]] = mapped_column(JSON, default=list)


class WaifuCP(BaseGroupModel):
    __tablename__ = "waifu_cp"

    affect: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)


class PWaifu(BaseGroupModel):
    __tablename__ = "waifu"

    waifu_list: Mapped[list[int]] = mapped_column(JSON, default=[])


class WaifuLock(BaseGroupModel):
    __tablename__ = "waifu_lock"

    lock: Mapped[dict] = mapped_column(JSON, default={})


class YinpaRecord(Model):
    __abstract__ = True

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    active_count: Mapped[int] = mapped_column(default=0)
    passive_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now
    )


class YinpaActive(YinpaRecord):
    __tablename__ = "yinpa_active"


class YinpaPassive(YinpaRecord):
    __tablename__ = "yinpa_passive"
