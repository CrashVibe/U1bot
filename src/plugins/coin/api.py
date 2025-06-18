from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import CoinRecord


async def get_coin(user_id: str) -> float:
    async with get_session() as session:
        result = await session.execute(
            select(CoinRecord).where(CoinRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        return record.coin if record else 0.0


async def get_count_coin(user_id: str) -> float:
    async with get_session() as session:
        result = await session.execute(
            select(CoinRecord).where(CoinRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        return record.count_coin if record else 0.0


async def add_coin(user_id: str, amount: float) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(CoinRecord).where(CoinRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record:
            record.coin += amount
            record.count_coin += amount
        else:
            record = CoinRecord(user_id=user_id, coin=amount, count_coin=amount)
            session.add(record)
        await session.commit()


async def set_coin(user_id: str, amount: float) -> None:
    async with get_session() as session:
        result = await session.execute(
            select(CoinRecord).where(CoinRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record:
            record.coin = amount
            await session.commit()
