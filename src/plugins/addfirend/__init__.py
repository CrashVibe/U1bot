# 取出管理员QQ号
import asyncio
import time

from nonebot import get_driver, logger, on_request
from nonebot.adapters.onebot.v11 import (
    Bot,
    FriendRequestEvent,
    GroupRequestEvent,
    RequestEvent,
)

# 获取管理员的id

# 获取超级用户的id
SUPERUSER_list = list(get_driver().config.superusers)


addfriend = on_request()


# 特殊账号
special_qqid = ["3862130847"]


def format_time(_time: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(_time))


@addfriend.handle()
async def _(bot: Bot, event: RequestEvent):
    if isinstance(event, GroupRequestEvent):
        if event.sub_type != "invite":
            return
        # 获取好友列表对比
        friend_list = await bot.get_friend_list()
        if event.user_id not in [friend["user_id"] for friend in friend_list]:
            await addfriend.finish("我们还是先成为好友再带我去别的地方吧~")
            return
        nickname = (await bot.get_stranger_info(user_id=event.user_id, no_cache=True))[
            "nickname"
        ]
        approve = True
        await bot.set_group_add_request(
            flag=event.flag, sub_type="invite", approve=approve
        )
        try:
            group_info = await bot.get_group_info(
                group_id=event.group_id, no_cache=True
            )
        except Exception:
            logger.exception("获取群信息失败")
        approve = group_info["member_count"] > 15 or event.group_id == 966016220
        msg = (
            "⚠收到一条拉群邀请:\n"
            f"flag: {event.flag}\n"
            f"user: {event.user_id}\n"
            f"name: {nickname}\n"
            f"group: {event.group_id}\n"
            f"name: {group_info['group_name']}\n"
            f"time: {format_time(event.time)}\n"
            f"人数: {group_info['member_count']}\n"
            f"自动同意/拒绝: {approve}\n"
            + ("" if approve else "原因：人数过少，已退出\n")
            + f"验证信息:\n"
            f"{event.comment}"
        )
        if not approve:
            await bot.send_group_msg(
                group_id=event.group_id,
                message=(
                    "由于机器人的群数量过多，对新的群要求人数超过15人以上，请见谅，正在退出中！"
                ),
            )
            await asyncio.sleep(1)
            await bot.set_group_leave(group_id=event.group_id)
    elif isinstance(event, FriendRequestEvent):
        nickname = (await bot.get_stranger_info(user_id=event.user_id, no_cache=True))[
            "nickname"
        ]
        approve = True
        msg = (
            "⚠收到一条好友请求:\n"
            f"flag: {event.flag}\n"
            f"user: {event.user_id}\n"
            f"name: {nickname}\n"
            f"time: {format_time(event.time)}\n"
            f"自动同意/拒绝: {approve}\n"
            f"验证信息:\n"
            f"{event.comment}"
        )
        await bot.set_friend_add_request(flag=event.flag, approve=approve)
    else:
        return
    for super_id in SUPERUSER_list:
        await bot.send_private_msg(user_id=int(super_id), message=msg)
