import httpx
from nonebot import logger, on_command
from nonebot.plugin import PluginMetadata

__help_version__ = "0.1.0"
__help_plugin_name__ = "网抑云"
__usage__ = """指令：网抑云 | 网易云热评  随机一条网易云热评"""

__plugin_meta__ = PluginMetadata(
    name=__help_plugin_name__,
    description="12 点啦，该网抑云啦！[哭]",
    usage=__usage__,
)
hitokoto_matcher = on_command("网抑云", aliases={"网易云热评"}, block=True)


@hitokoto_matcher.handle()
async def hitokoto():
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.get(r"https://international.v1.hitokoto.cn/?c=j")
    if response.is_error:
        logger.error("获取网抑云失败咯，请稍后再试...")
        return
    logger.info(response.text)
    data = response.json()
    await hitokoto_matcher.finish(data["hitokoto"] + " ——《" + data["creator"] + "》")
