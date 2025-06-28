# 获取所有群消息

import asyncio

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.permission import SUPERUSER

# 事件响应函数
rlist = on_command("removegrouplist", permission=SUPERUSER)


def condition(group_info):
    member_count = group_info["member_count"]
    group_name: str = group_info["group_name"]
    return (
        member_count < 10
        or (
            ("机器人" in group_name or "ai" in group_name or "test" in group_name)
            and len(group_name) < 8
        )
        or group_name.count("、") >= 2
    ) and group_info["group_id"] != 966016220


async def get_group_member_list_safe(bot: Bot, group_id: int) -> list[int]:
    """安全获取群成员列表"""
    try:
        group_member_list = await bot.get_group_member_list(group_id=group_id)
        return [member["user_id"] for member in group_member_list]
    except Exception as e:
        logger.warning(f"获取群 {group_id} 成员列表失败: {e}")
        return []


async def batch_get_group_members(
    bot: Bot, group_list: list, batch_size: int = 10
) -> dict[int, list[int]]:
    """并发批量获取群成员列表"""
    group_member_lists = {}
    total_groups = len(group_list)

    for i in range(0, total_groups, batch_size):
        batch = group_list[i : i + batch_size]

        # 并发获取这一批群的成员列表
        tasks = [
            get_group_member_list_safe(bot, group_info["group_id"])
            for group_info in batch
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for j, (group_info, result) in enumerate(zip(batch, results)):
            if isinstance(result, Exception):
                logger.error(f"获取群 {group_info['group_id']} 成员列表异常: {result}")
                group_member_lists[group_info["group_id"]] = []
            else:
                group_member_lists[group_info["group_id"]] = result

        # 输出进度
        completed = min(i + batch_size, total_groups)
        progress = completed / total_groups * 100
        logger.info(f"获取群成员列表进度: {progress:.1f}% ({completed}/{total_groups})")

        # 批次间短暂延迟，避免频率限制
        if i + batch_size < total_groups:
            await asyncio.sleep(0.5)

    return group_member_lists


async def analyze_groups(
    bot: Bot, group_list: list, friend_list_qq: list[int]
) -> tuple[list[dict], list[dict]]:
    """并发分析群组，返回需要处理的群组"""
    # 检查人数条件的群组
    member_count_groups = []

    # 检查好友条件的群组
    no_friend_groups = []

    # 并发获取所有群成员列表
    group_member_lists = await batch_get_group_members(bot, group_list)

    friend_set = set(friend_list_qq)

    # 分析每个群组
    for group_info in group_list:
        group_id = group_info["group_id"]
        member_count = group_info["member_count"]
        group_name = group_info["group_name"]

        # 检查人数条件
        if condition(group_info):
            member_count_groups.append(
                {
                    "group_id": group_id,
                    "group_name": group_name,
                    "member_count": member_count,
                    "reason": "人数或名称条件",
                }
            )

        # 检查好友条件
        group_member_list_qq = group_member_lists.get(group_id, [])
        group_member_set = set(group_member_list_qq)
        intersection = friend_set & group_member_set

        if not intersection:
            no_friend_groups.append(
                {
                    "group_id": group_id,
                    "group_name": group_name,
                    "member_count": member_count,
                    "reason": "无共同好友",
                }
            )

        # 输出分析进度
        progress = (group_list.index(group_info) + 1) / len(group_list) * 100
        intersection_ratio = len(intersection) / len(friend_set) if friend_set else 0
        logger.info(
            f"分析进度: {progress:.1f}% 群:{group_id} 成员:{member_count} "
            f"好友交集:{len(intersection)} 占比:{intersection_ratio:.2f}"
        )

    return member_count_groups, no_friend_groups


@rlist.handle()
async def _(bot: Bot):
    await rlist.send("🔍 开始分析群组...")

    try:
        # 获取群列表和好友列表
        group_list = await bot.get_group_list()
        friend_list = await bot.get_friend_list()
        friend_list_qq = [friend["user_id"] for friend in friend_list]

        await rlist.send(
            f"📊 共有 {len(group_list)} 个群组，{len(friend_list_qq)} 个好友，开始并发分析..."
        )

        # 并发分析群组
        member_count_groups, no_friend_groups = await analyze_groups(
            bot, group_list, friend_list_qq
        )

        # 合并输出结果
        messages = []

        if member_count_groups:
            messages.append(
                f"📉 人数/名称条件不符合的群组 ({len(member_count_groups)} 个):"
            )
            for group in member_count_groups[:10]:  # 最多显示10个
                messages.append(
                    f"  群号: {group['group_id']} | 群名: {group['group_name']} | "
                    f"成员: {group['member_count']} | 原因: {group['reason']}"
                )
            if len(member_count_groups) > 10:
                messages.append(f"  ... 还有 {len(member_count_groups) - 10} 个群组")
        else:
            messages.append("✅ 没有找到人数/名称条件不符合的群组")

        messages.append("")  # 空行分隔

        if no_friend_groups:
            messages.append(f"👥 无共同好友的群组 ({len(no_friend_groups)} 个):")
            for group in no_friend_groups[:10]:  # 最多显示10个
                messages.append(
                    f"  群号: {group['group_id']} | 群名: {group['group_name']} | "
                    f"成员: {group['member_count']} | 原因: {group['reason']}"
                )
            if len(no_friend_groups) > 10:
                messages.append(f"  ... 还有 {len(no_friend_groups) - 10} 个群组")
        else:
            messages.append("✅ 没有找到无共同好友的群组")

        # 统计信息
        total_problematic = len(member_count_groups) + len(no_friend_groups)
        messages.append(f"\n📈 统计: 共 {total_problematic} 个问题群组")

        # 分批发送消息，避免消息过长
        current_message = ""
        for msg in messages:
            if len(current_message + msg + "\n") > 4000:  # 避免消息过长
                await rlist.send(current_message.strip())
                current_message = msg + "\n"
            else:
                current_message += msg + "\n"

        if current_message.strip():
            await rlist.send(current_message.strip())

    except Exception as e:
        logger.error(f"分析群组时发生错误: {e}")
        await rlist.send(f"❌ 分析过程中发生错误: {e}")

    await rlist.finish("✅ 群组分析完成!")


async def leave_group_safe(bot: Bot, group_id: int) -> tuple[int, bool, str]:
    """安全退出群组"""
    try:
        await bot.set_group_leave(group_id=group_id)
        return group_id, True, "成功退出"
    except Exception as e:
        logger.warning(f"退出群 {group_id} 失败: {e}")
        return group_id, False, str(e)


async def batch_leave_groups(
    bot: Bot, groups_to_remove: list[dict], batch_size: int = 5
) -> tuple[list[dict], list[dict]]:
    """并发批量退出群组"""
    success_groups = []
    failed_groups = []
    total_groups = len(groups_to_remove)

    for i in range(0, total_groups, batch_size):
        batch = groups_to_remove[i : i + batch_size]

        # 并发退出这一批群组
        tasks = [leave_group_safe(bot, group["group_id"]) for group in batch]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        for group, result in zip(batch, results):
            if isinstance(result, Exception):
                failed_groups.append({**group, "error": str(result)})
            elif isinstance(result, tuple) and len(result) == 3:
                group_id, success, message = result
                if success:
                    success_groups.append({**group, "message": message})
                else:
                    failed_groups.append({**group, "error": message})
            else:
                failed_groups.append({**group, "error": "未知结果格式"})

        # 输出进度
        completed = min(i + batch_size, total_groups)
        progress = completed / total_groups * 100
        logger.info(f"退出群组进度: {progress:.1f}% ({completed}/{total_groups})")

        # 批次间延迟，避免频率限制
        if i + batch_size < total_groups:
            await asyncio.sleep(1)

    return success_groups, failed_groups


rgroup = on_command("removegroup", permission=SUPERUSER)


@rgroup.handle()
async def _(bot: Bot):
    await rgroup.send("🚀 开始批量移除群组...")

    try:
        # 获取群列表和好友列表
        group_list = await bot.get_group_list()
        friend_list = await bot.get_friend_list()
        friend_list_qq = [friend["user_id"] for friend in friend_list]

        await rgroup.send(f"📊 共有 {len(group_list)} 个群组，开始分析...")

        # 并发分析群组
        member_count_groups, no_friend_groups = await analyze_groups(
            bot, group_list, friend_list_qq
        )

        # 合并要移除的群组
        all_groups_to_remove = member_count_groups + no_friend_groups

        if not all_groups_to_remove:
            await rgroup.finish("✅ 没有需要移除的群组")

        await rgroup.send(f"⚠️ 即将移除 {len(all_groups_to_remove)} 个群组...")

        # 并发批量退出群组
        success_groups, failed_groups = await batch_leave_groups(
            bot, all_groups_to_remove
        )

        # 合并输出结果
        messages = []

        if success_groups:
            messages.append(f"✅ 成功退出的群组 ({len(success_groups)} 个):")
            for group in success_groups[:15]:  # 最多显示15个
                messages.append(
                    f"  ✓ {group['group_id']} | {group['group_name']} | "
                    f"成员:{group['member_count']} | {group['reason']}"
                )
            if len(success_groups) > 15:
                messages.append(f"  ... 还有 {len(success_groups) - 15} 个群组")

        if failed_groups:
            messages.append(f"\n❌ 退出失败的群组 ({len(failed_groups)} 个):")
            for group in failed_groups[:10]:  # 最多显示10个
                messages.append(
                    f"  ✗ {group['group_id']} | {group['group_name']} | "
                    f"错误: {group['error'][:50]}..."
                )
            if len(failed_groups) > 10:
                messages.append(f"  ... 还有 {len(failed_groups) - 10} 个群组")

        # 统计信息
        messages.append(
            f"\n📈 统计: 成功 {len(success_groups)} 个，失败 {len(failed_groups)} 个"
        )

        # 分批发送消息
        current_message = ""
        for msg in messages:
            if len(current_message + msg + "\n") > 4000:
                await rgroup.send(current_message.strip())
                current_message = msg + "\n"
            else:
                current_message += msg + "\n"

        if current_message.strip():
            await rgroup.send(current_message.strip())

    except Exception as e:
        logger.error(f"移除群组时发生错误: {e}")
        await rgroup.send(f"❌ 移除过程中发生错误: {e}")

    await rgroup.finish("🎯 群组移除操作完成!")
