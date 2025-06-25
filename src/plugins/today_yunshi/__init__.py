"""这是一个今日运势插件，可以查看今日运势。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata

from .data_source import luck_result

__plugin_meta__ = PluginMetadata(
    name="今日运势",
    description="看看今天的运势吧",
    usage='发送"今日运势"或"运势"',
)

Luck = on_command("今日运势", aliases={"运势"}, block=True)


@Luck.handle()
async def luck(bot: Bot, event: MessageEvent):
    result = await luck_result(str(event.user_id))
    await bot.send(event, result, reply_message=True)
