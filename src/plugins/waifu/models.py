from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import require
from sqlalchemy.orm.properties import MappedColumn

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model
from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import mapped_column


def get_current_time():
    """获取当前时间（亚洲/上海时区）"""
    return datetime.now(ZoneInfo("Asia/Shanghai"))


class WaifuRelationship(Model):
    """娶群友关系表 - 记录用户之间的CP关系"""

    __tablename__ = "waifu_relationships"

    id: MappedColumn[int]= mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)
    partner_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime, default=get_current_time, nullable=False
    )

    __table_args__ = (
        # 确保同一群组中，一个用户只能有一个CP
        UniqueConstraint("group_id", "user_id", name="uq_group_user"),
        # 确保同一群组中，一个用户不能被多个人娶
        UniqueConstraint("group_id", "partner_id", name="uq_group_partner"),
        # 添加索引优化查询性能
        Index("ix_group_user", "group_id", "user_id"),
        Index("ix_group_partner", "group_id", "partner_id"),
        Index("ix_created_at", "created_at"),
    )


class WaifuProtectedUser(Model):
    """受保护用户表 - 记录不能被娶的用户"""

    __tablename__ = "waifu_protected_users"

    id: MappedColumn[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)
    user_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime, default=get_current_time, nullable=False
    )

    __table_args__ = (
        # 确保同一群组中，同一用户不能重复添加保护
        UniqueConstraint("group_id", "user_id", name="uq_protected_group_user"),
        Index("ix_protected_group_user", "group_id", "user_id"),
    )


class WaifuLock(Model):
    """用户锁定表 - 记录用户的锁定状态"""

    __tablename__ = "waifu_locks"

    id: MappedColumn[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)
    user_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)
    lock_type: MappedColumn[str] = mapped_column(
        String(50), nullable=False, default="general"
    )
    expires_at: MappedColumn[datetime] = mapped_column(
        DateTime, nullable=True
    )  # 过期时间，None表示永久
    is_active: MappedColumn[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime, default=get_current_time, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "group_id", "user_id", "lock_type", name="uq_lock_group_user_type"
        ),
        Index("ix_lock_group_user", "group_id", "user_id"),
        Index("ix_lock_expires", "expires_at"),
        Index("ix_lock_active", "is_active"),
    )


class YinpaRecord(Model):
    """透群友记录表"""

    __tablename__ = "yinpa_records"

    id: MappedColumn[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False, index=True)
    active_user_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)  # 主动方
    passive_user_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)  # 被动方
    success: MappedColumn[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # 是否成功
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime, default=get_current_time, nullable=False
    )

    __table_args__ = (
        Index("ix_yinpa_group_active", "group_id", "active_user_id"),
        Index("ix_yinpa_group_passive", "group_id", "passive_user_id"),
        Index("ix_yinpa_created", "created_at"),
        Index("ix_yinpa_success", "success"),
    )


class WaifuDailyReset(Model):
    """每日重置记录表 - 记录每日重置的时间戳"""

    __tablename__ = "waifu_daily_resets"

    id: MappedColumn[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    group_id: MappedColumn[int] = mapped_column(BigInteger, nullable=False)
    reset_date: MappedColumn[datetime] = mapped_column(
        DateTime, nullable=False
    )  # 重置日期（只到日期，不包含时间）
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime, default=get_current_time, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("group_id", "reset_date", name="uq_group_reset_date"),
        Index("ix_reset_group_date", "group_id", "reset_date"),
    )


class YinpaActive(Model):
    """透群友主动记录表"""

    __tablename__ = "yinpa_active"

    user_id: MappedColumn[int] = mapped_column(BigInteger, primary_key=True)
    active_count: MappedColumn[int] = mapped_column(default=0, nullable=False)
    updated_at: MappedColumn[datetime] = mapped_column(
        DateTime, default=get_current_time, onupdate=get_current_time, nullable=False
    )


class YinpaPassive(Model):
    """透群友被动记录表"""

    __tablename__ = "yinpa_passive"

    user_id: MappedColumn[int] = mapped_column(BigInteger, primary_key=True)
    passive_count: MappedColumn[int] = mapped_column(default=0, nullable=False)
    updated_at: MappedColumn[datetime] = mapped_column(
        DateTime, default=get_current_time, onupdate=get_current_time, nullable=False
    )
