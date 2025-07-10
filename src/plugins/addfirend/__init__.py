# 取出管理员QQ号
import time

from nonebot import get_bots, get_driver, logger, on_request
from nonebot.adapters.onebot.v11 import (
    Bot,
    FriendRequestEvent,
    GroupRequestEvent,
    RequestEvent,
)

# 获取超级用户的id
SUPERUSER_list = list(get_driver().config.superusers)

# 机器人优先级配置 (数字越大优先级越高)
BOT_PRIORITY = {
    1184441051: 1,  # 优先级最低
    467739286: 2,  # 优先级中等
    3862130847: 3,  # 优先级最高
}


async def check_bot_priority_in_group(
    group_id: int, current_bot_id: int
) -> tuple[bool, str]:
    """
    检查当前机器人在群组中的优先级
    返回: (是否应该进群, 原因)
    """
    # 跳过免疫群组
    if group_id == 966016220 or group_id == 713478803:
        return True, "免疫群组，直接进入"

    bots = get_bots()
    current_bot_priority = BOT_PRIORITY.get(current_bot_id, 0)

    # 检查其他机器人是否在这个群组中
    for bot_id_str, bot in bots.items():
        bot_id = int(bot_id_str)

        # 跳过当前机器人
        if bot_id == current_bot_id:
            continue

        try:
            # 检查这个机器人是否在目标群组中
            group_list = await bot.get_group_list()
            group_ids = [group["group_id"] for group in group_list]

            if group_id in group_ids:
                other_bot_priority = BOT_PRIORITY.get(bot_id, 0)
                logger.info(
                    f"发现机器人 {bot_id} 已在群 {group_id} 中，优先级: {other_bot_priority}"
                )

                # 比较优先级
                if current_bot_priority > other_bot_priority:
                    # 当前机器人优先级更高，让其他机器人退群
                    logger.info(
                        f"当前机器人 {current_bot_id} 优先级 {current_bot_priority} > 机器人 {bot_id} 优先级 {other_bot_priority}，让其退群"
                    )
                    try:
                        await bot.set_group_leave(group_id=group_id)
                        logger.info(f"成功让机器人 {bot_id} 退出群 {group_id}")
                    except Exception as e:
                        logger.warning(f"让机器人 {bot_id} 退出群 {group_id} 失败: {e}")
                elif current_bot_priority < other_bot_priority:
                    # 当前机器人优先级更低，拒绝进群
                    return (
                        False,
                        f"群内已有更高优先级机器人 {bot_id} (优先级: {other_bot_priority})",
                    )
                else:
                    # 优先级相同，拒绝进群
                    return (
                        False,
                        f"群内已有相同优先级机器人 {bot_id} (优先级: {other_bot_priority})",
                    )

        except Exception as e:
            logger.warning(f"检查机器人 {bot_id} 群组列表失败: {e}")

    return True, "没有发现冲突的机器人"


addfriend = on_request()


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
            try:
                await bot.send_private_msg(
                    user_id=event.user_id,
                    message="我们还是先成为好友再带我去别的地方吧~",
                )
            except Exception as e:
                logger.warning(f"发送私信失败 (用户: {event.user_id}): {e}")
            return
        nickname = (await bot.get_stranger_info(user_id=event.user_id, no_cache=True))[
            "nickname"
        ]

        try:
            group_info = await bot.get_group_info(
                group_id=event.group_id, no_cache=True
            )
        except Exception:
            logger.exception("获取群信息失败")
            return

        # 检查机器人优先级
        current_bot_id = int(bot.self_id)
        can_join, priority_reason = await check_bot_priority_in_group(
            event.group_id, current_bot_id
        )

        # 基本条件检查：人数 > 15 或者是免疫群组
        basic_approve = (
            group_info["member_count"] > 15
            or event.group_id == 966016220
            or event.group_id == 713478803
        )

        # 最终决定：基本条件 AND 优先级检查
        approve = basic_approve and can_join

        # 构建消息
        msg = (
            "⚠收到一条拉群邀请:\n"
            f"flag: {event.flag}\n"
            f"user: {event.user_id}\n"
            f"name: {nickname}\n"
            f"group: {event.group_id}\n"
            f"name: {group_info['group_name']}\n"
            f"time: {format_time(event.time)}\n"
            f"人数: {group_info['member_count']}\n"
            f"机器人优先级检查: {priority_reason}\n"
            f"自动同意/拒绝: {approve}\n"
        )

        # 添加拒绝原因
        if not approve:
            reasons = []
            if not basic_approve:
                reasons.append("人数过少")
            if not can_join:
                reasons.append(f"优先级冲突 ({priority_reason})")
            msg += f"拒绝原因: {', '.join(reasons)}\n"

        msg += f"验证信息:\n{event.comment}"

        # 设置群邀请结果
        await bot.set_group_add_request(
            flag=event.flag, sub_type="invite", approve=approve
        )

        # 如果拒绝进群，发送说明消息
        if not approve:
            try:
                if not can_join:
                    await bot.send_private_msg(
                        user_id=event.user_id,
                        message=f"抱歉，由于群内已有其他机器人且优先级更高，无法进入该群。原因: {priority_reason}",
                    )
                else:
                    await bot.send_private_msg(
                        user_id=event.user_id,
                        message="由于机器人的群数量过多，对新的群要求人数超过15人以上，请见谅！",
                    )
            except Exception as e:
                logger.warning(f"发送拒绝私信失败 (用户: {event.user_id}): {e}")
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
