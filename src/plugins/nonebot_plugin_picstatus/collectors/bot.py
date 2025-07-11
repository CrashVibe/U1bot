import asyncio
from dataclasses import dataclass
from datetime import datetime

from nonebot import get_bots
from nonebot.adapters import Bot as BaseBot
from nonebot.matcher import current_bot

from ..config import config
from ..misc_statistics import (
    bot_connect_time,
    bot_info_cache,
    recv_num,
    send_num,
)
from ..util import format_timedelta
from . import normal_collector

try:
    from nonebot.adapters.milky import Bot as MilkyBot
except ImportError:
    MilkyBot = None


@dataclass
class BotStatus:
    self_id: str
    adapter: str
    nick: str
    bot_connected: str
    msg_rec: str
    msg_sent: str


async def get_bot_status(bot: BaseBot, now_time: datetime) -> BotStatus:
    nick = (
        ((info := bot_info_cache[bot.self_id]).user_displayname or info.user_name)
        if (not config.ps_use_env_nick) and (bot.self_id in bot_info_cache)
        else next(iter(config.nickname), None)
    ) or "Bot"
    bot_connected = (
        format_timedelta(now_time - t)
        if (t := bot_connect_time.get(bot.self_id))
        else "未知"
    )

    msg_rec = recv_num.get(bot.self_id)
    msg_sent = send_num.get(bot.self_id)
    msg_rec = "未知" if (msg_rec is None) else str(msg_rec)
    msg_sent = "未知" if (msg_sent is None) else str(msg_sent)

    return BotStatus(
        self_id=bot.self_id,
        adapter=bot.adapter.get_name(),
        nick=nick,
        bot_connected=bot_connected,
        msg_rec=msg_rec,
        msg_sent=msg_sent,
    )


@normal_collector()
async def bots() -> list[BotStatus]:
    now_time = datetime.now().astimezone()
    return (
        [await get_bot_status(current_bot.get(), now_time)]
        if config.ps_show_current_bot_only
        else await asyncio.gather(
            *(get_bot_status(bot, now_time) for bot in get_bots().values()),
        )
    )
