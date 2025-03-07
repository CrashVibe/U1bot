from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna

from .config import DEBUG, QWEATHER_APIKEY, QWEATHER_APITYPE, Config
from .render_pic import render
from .weather_data import CityNotFoundError, ConfigError, Weather

__plugin_meta__ = PluginMetadata(
    name="和风天气",
    description="和风天气图片显示插件",
    usage="天气地名 / 地名天气",
    type="application",
    homepage="https://github.com/kexue-z/nonebot-plugin-heweather",
    config=Config,
)


if DEBUG:
    logger.debug("将会保存图片到 weather.png")


weather = on_alconna(Alconna("天气", Args["city", str]), block=True)
weather.shortcut(r"^(?P<city>.+)天气$", {"args": ["{city}"], "fuzzy": False})
weather.shortcut(r"^天气(?P<city>.+)$", {"args": ["{city}"], "fuzzy": False})


@weather.handle()
async def _(matcher: Matcher, city: str):
    if QWEATHER_APIKEY is None or QWEATHER_APITYPE is None:
        raise ConfigError("请设置 qweather_apikey 和 qweather_apitype")

    w_data = Weather(city_name=city, api_key=QWEATHER_APIKEY, api_type=QWEATHER_APITYPE)
    try:
        await w_data.load_data()
    except CityNotFoundError:
        logger.warning(f"找不到城市: {city}")
        matcher.block = False
        await matcher.finish()
    img = await render(w_data)
    if DEBUG:
        debug_save_img(img)

    await UniMessage.image(raw=img).send()


def debug_save_img(img: bytes) -> None:
    from io import BytesIO

    from PIL import Image

    logger.debug("保存图片到 weather.png")
    a = Image.open(BytesIO(img))
    a.save("weather.png", format="PNG")
