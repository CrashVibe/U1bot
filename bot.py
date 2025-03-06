import asyncio
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # avoid sphinx autodoc resolve annotation failed
    # because loguru module do not have `Logger` class actually
    from loguru import Record

import nonebot
from nonebot import logger
from nonebot.log import default_format, logger_id


def default_filter(record: "Record"):
    """默认的日志过滤器，根据 `config.log_level` 配置改变日志等级。"""
    log_level = record["extra"].get("nonebot_log_level", "INFO")
    levelno = logger.level(log_level).no if isinstance(log_level, str) else log_level

    return record["level"].no >= levelno


# 移除 NoneBot 默认的日志处理器
logger.remove(logger_id)
# 添加新的日志处理器
logger.add(
    sys.stdout,
    level=0,
    diagnose=True,
    format=default_format,
    filter=default_filter,
)

from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.exception import IgnoredException

nonebot.init()
app = nonebot.get_asgi()
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)


nonebot.load_from_toml("pyproject.toml")
from nonebot.message import event_preprocessor

from U1.database import Channel


async def get_channel(group_id: str):
    return await Channel.get_or_none(guildId=group_id)


@event_preprocessor
async def _(bot: Bot, event: GroupMessageEvent):
    "防止机器人自言自语"
    # 检测是否是机器人自己发的消息
    bots = nonebot.get_bots()
    if event.get_user_id() in bots.keys():
        raise IgnoredException("机器人自己发的消息，忽略")
    "防止双发"
    bot_qqid = bot.self_id
    if event.to_me:
        return
    channel = await get_channel(str(event.group_id))
    if channel is None:
        attempts = 0
        while attempts < 3:
            channel = await get_channel(str(event.group_id))
            if channel is not None:
                break  # 重试直到找到频道
            attempts += 1
            if attempts == 3:
                raise IgnoredException("未找到频道，忽略")
            await asyncio.sleep(0.5)
    if channel is not None and channel.assignee != bot_qqid:
        raise IgnoredException("机器人不是频道指定的机器人，忽略")


if __name__ == "__main__":
    nonebot.run()
