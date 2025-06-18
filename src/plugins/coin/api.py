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


async def add_coin(user_id: str, amount: float) -> float:
    """增加金币，返回剩余金币数量"""
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
        await session.refresh(record)
        return record.coin


async def set_coin(user_id: str, amount: float) -> float:
    """设置金币数量，返回设置后的金币数量"""
    async with get_session() as session:
        result = await session.execute(
            select(CoinRecord).where(CoinRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record:
            record.coin = amount
        else:
            record = CoinRecord(user_id=user_id, coin=amount, count_coin=amount)
            session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.coin


async def subtract_coin(user_id: str, amount: float) -> tuple[bool, float]:
    """
    减少金币，返回操作是否成功和剩余金币数量

    Args:
        user_id: 用户ID
        amount: 要减少的金币数量

    Returns:
        tuple[bool, float]: (是否成功, 剩余金币数量)
        如果余额不足，返回 (False, 当前余额)
        如果成功扣除，返回 (True, 剩余余额)
    """
    async with get_session() as session:
        result = await session.execute(
            select(CoinRecord).where(CoinRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()

        # 如果用户不存在或余额不足
        current_coin = record.coin if record else 0.0
        if current_coin < amount:
            return False, current_coin

        # 扣除金币
        if record:
            record.coin -= amount
        else:
            # 理论上不会执行到这里，因为上面已经检查了余额
            record = CoinRecord(user_id=user_id, coin=-amount, count_coin=0)
            session.add(record)

        await session.commit()
        await session.refresh(record)
        return True, record.coin
