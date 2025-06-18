from nonebot_plugin_orm import Model
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class CoinRecord(Model):
    __tablename__ = "coin_coinrecord"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32))
    coin: Mapped[float] = mapped_column(Float, default=0)
    count_coin: Mapped[float] = mapped_column(Float, default=0)
