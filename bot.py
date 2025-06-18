import asyncio
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loguru import Record

import nonebot
from nonebot import logger
from nonebot.log import default_format, logger_id


def default_filter(record: "Record"):
    """默认的日志过滤器，根据 `config.log_level` 配置改变日志等级。"""
    log_level = record["extra"].get("nonebot_log_level", "INFO")
    levelno = logger.level(log_level).no if isinstance(log_level, str) else log_level

    return record["level"].no >= levelno


log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

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


logger.add(
    f"{log_dir}/" + "{time}.log",  # 传入函数，每天自动更新日志路径
    level="WARNING",
    format=default_format,
    rotation="00:00",
    retention="7 days",
    encoding="utf-8",
    enqueue=True,
)


from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.exception import IgnoredException

nonebot.init()
app = nonebot.get_asgi()
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11Adapter)

@driver.on_startup
async def connect_db():
    from U1.database import connect

    await connect()

@driver.on_shutdown
async def disconnect_db():
    from U1.database import disconnect

    await disconnect()

nonebot.load_from_toml("pyproject.toml")
from nonebot.message import event_preprocessor

from U1.model import Channel


async def get_channel(group_id: str):
    return await Channel.get_or_none(guildId=group_id)


@event_preprocessor
async def _(bot: Bot, event: GroupMessageEvent):
    "防止机器人自言自语"
    bot_qqid = bot.self_id
    if event.to_me:
        return
    channel = await get_channel(str(event.group_id))
    if channel is None:
        for _ in range(3):
            channel = await get_channel(str(event.group_id))
            if channel is not None:
                break  # 重试直到找到频道
            await asyncio.sleep(0.5)
    if channel is None:
        raise IgnoredException("未找到频道，忽略")
    if channel.assignee != bot_qqid:
        raise IgnoredException("机器人不是频道指定的机器人，忽略")


if __name__ == "__main__":
    nonebot.run()
