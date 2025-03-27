from nonebot import on_fullmatch, on_startswith
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from .data_source import get_morning_msg, get_night_msg
from .scheduler import scheduler

__all__ = ["scheduler"]

morning = on_startswith(
    msg=(
        "早安",
        "早哇",
        "起床",
        "早上好",
        "ohayo",
        "哦哈哟",
        "お早う",
        "good morning",
    )
)
morning_2 = on_fullmatch(msg="早")

night = on_startswith(
    msg=(
        "晚安",
        "晚好",
        "睡觉",
        "晚上好",
        "oyasuminasai",
        "おやすみなさい",
        "good evening",
        "good night",
    )
)

night_2 = on_fullmatch(msg="晚")


@morning.handle()
@morning_2.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id
    gid = event.group_id

    await morning.finish(await get_morning_msg(uid, gid))


@night.handle()
@night_2.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    uid = event.user_id
    gid = event.group_id

    await night.finish(await get_night_msg(uid, gid))
