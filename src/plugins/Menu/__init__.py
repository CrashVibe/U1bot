import base64
import re
import traceback
from pathlib import Path

import ujson as json
from nonebot import on_command
from nonebot.adapters.milky import Bot
from nonebot.adapters.milky import Message
from nonebot.adapters.milky import MessageSegment
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_htmlrender import md_to_pic

dir_path = Path(__file__).parent

markdown_path = dir_path / "markdown"


async def get_reply(name: str):
    return await md_to_pic(
        md_path=str(markdown_path / f"{name}.md"), css_path=str(dir_path / "dark.css")
    )


menu = on_command("菜单", aliases={"cd", "功能", "帮助", "help"}, block=True)

with open(dir_path / "main.png", mode="rb") as file:
    img_bytes = file.read()
base64_str = f"base64://{base64.b64encode(img_bytes).decode()}"

# 将 json 所有功能缓存 base64
cache_plugin_img: dict = {}

with open(dir_path / "plugin.json", encoding="utf-8") as file:
    content = file.read()
    plugin_list: dict[str, str] = json.loads(content)


@menu.handle()
async def _(bot: Bot, matcher: Matcher, arg: Message = CommandArg()):
    msg = arg.extract_plain_text().strip()

    if not msg:  # 参数为空，主菜单
        await matcher.finish(MessageSegment.image(base64_str))

    match_result = re.match(r"^(?P<name>.*?)$", msg)
    if not match_result:
        return
    plugin_name_result = None
    plugin_name: str = match_result["name"]
    if plugin_name.isdigit():
        plugin_name_result = plugin_list.get(plugin_name)
        if plugin_name_result is None:
            await matcher.finish("插件序号不存在")
    else:
        for _, value in plugin_list.items():
            if plugin_name in value:
                plugin_name_result = value
    if not plugin_name_result:
        await matcher.finish("插件名过于模糊或不存在")

    if plugin_name_result not in cache_plugin_img:
        try:
            result = await get_reply(plugin_name_result)
            if plugin_name_result not in cache_plugin_img and isinstance(result, bytes):
                cache_plugin_img[plugin_name_result] = (
                    f"base64://{base64.b64encode(result).decode()}"
                )
        except Exception:
            logger.warning(traceback.format_exc())
            await matcher.finish("出错了，请稍后再试")
    result = cache_plugin_img[plugin_name_result]

    if isinstance(result, str) and not result.startswith("base64://"):
        await matcher.finish(result)

    if isinstance(bot, Bot):
        await matcher.finish(MessageSegment.image(result))
    else:
        raise NotImplementedError
