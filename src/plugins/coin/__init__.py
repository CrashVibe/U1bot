from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import CoinRecord

coin = on_command("coin", aliases={"金币", "余额"}, priority=5)


@coin.handle()
async def handle_coin(event: MessageEvent, args=CommandArg()):
    user_id = str(event.user_id)
    async with get_session() as session:
        result = await session.execute(
            select(CoinRecord).where(CoinRecord.user_id == user_id)
        )
        record = result.scalar_one_or_none()
        if record:
            await coin.finish(
                f"你当前拥有金币：{record.coin}\n历史总金币：{record.count_coin}"
            )
        else:
            await coin.finish("你还没有金币记录。")
