from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from U1.database import Model


class Channel(Model):
    __table_args__ = (UniqueConstraint("platform", "flag"),)

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    platform: Mapped[str] = mapped_column(String(255))
    flag: Mapped[int | None] = mapped_column(BigInteger, default=0, nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guildId: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locales: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
