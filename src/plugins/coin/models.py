from nonebot_plugin_orm import Model
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm.properties import MappedColumn


class CoinRecord(Model):
    __tablename__ = "coin_coinrecord"

    id: MappedColumn[int] = mapped_column(Integer, primary_key=True)
    user_id: MappedColumn[str] = mapped_column(String(32))
    coin: MappedColumn[float] = mapped_column(Float, default=0)
    count_coin: MappedColumn[float] = mapped_column(Float, default=0)
