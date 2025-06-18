# 导入插件方法
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from U1.database import Model


class cave_models(Model):
    """
    Model representing the cave_models table in the database.

    Attributes:
        id (int): The primary key of the cave model.
        details (str): The details of the cave model.
        user_id (int): The user ID associated with the cave model.
        time (datetime): The timestamp when the cave model was created.
    """

    __tablename__ = "cave_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    details: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(BigInteger)
    time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)

