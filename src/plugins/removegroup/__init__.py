# 获取所有群消息

import asyncio

from nonebot import get_bots, logger, on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.exception import FinishedException
from nonebot.permission import SUPERUSER

# 机器人优先级配置 (数字越大优先级越高)
BOT_PRIORITY = {
    1184441051: 1,  # 优先级最低
    467739286: 2,  # 优先级中等
    3862130847: 3,  # 优先级最高
}

# 事件响应函数
rlist = on_command("removegrouplist", permission=SUPERUSER)


def condition(group_info):
    member_count = group_info["member_count"]
    group_name: str = group_info["group_name"]
    return (
        (
            member_count < 10
            or (
                ("机器人" in group_name or "ai" in group_name or "test" in group_name)
                and len(group_name) < 8
            )
            or group_name.count("、") >= 2
        )
        and group_info["group_id"] != 966016220
        and group_info["group_id"] != 713478803
    )


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

    except FinishedException:
        # finish() 抛出的异常，正常流程，不处理
        raise
    except Exception as e:
        logger.error(f"分析群组时发生错误: {e}")
        await rlist.send(f"❌ 分析过程中发生错误: {e}")
        return

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

    except FinishedException:
        # finish() 抛出的异常，正常流程，不处理
        raise
    except Exception as e:
        logger.error(f"移除群组时发生错误: {e}")
        await rgroup.send(f"❌ 移除过程中发生错误: {e}")

    await rgroup.finish("🎯 群组移除操作完成!")


async def get_all_bots_groups() -> dict[int, list[dict]]:
    """获取所有机器人的群组信息"""
    bots = get_bots()
    all_bot_groups = {}

    for bot_id, bot in bots.items():
        try:
            # 将bot_id转换为整数
            bot_id_int = int(bot_id)
            group_list = await bot.get_group_list()
            all_bot_groups[bot_id_int] = group_list
            logger.info(f"机器人 {bot_id_int} 加入了 {len(group_list)} 个群组")
        except Exception as e:
            logger.error(f"获取机器人 {bot_id} 群组列表失败: {e}")
            all_bot_groups[int(bot_id)] = []

    return all_bot_groups


async def find_duplicate_groups(
    all_bot_groups: dict[int, list[dict]],
) -> dict[int, list[int]]:
    """查找重复的群组"""
    group_to_bots = {}  # {group_id: [bot_id1, bot_id2, ...]}

    # 收集所有群组和对应的机器人
    for bot_id, groups in all_bot_groups.items():
        for group in groups:
            group_id = group["group_id"]
            # 跳过免疫群组
            if group_id == 966016220 or group_id == 713478803:
                continue
            if group_id not in group_to_bots:
                group_to_bots[group_id] = []
            group_to_bots[group_id].append(bot_id)

    # 找出有多个机器人的群组
    duplicate_groups = {
        group_id: bot_list
        for group_id, bot_list in group_to_bots.items()
        if len(bot_list) > 1
    }

    return duplicate_groups


async def determine_bots_to_remove(
    duplicate_groups: dict[int, list[int]],
) -> list[tuple[int, int]]:
    """确定需要移除的机器人"""
    bots_to_remove = []  # [(bot_id, group_id), ...]

    for group_id, bot_list in duplicate_groups.items():
        # 根据优先级排序，优先级高的在前
        sorted_bots = sorted(
            bot_list, key=lambda x: BOT_PRIORITY.get(x, 0), reverse=True
        )

        # 保留优先级最高的机器人，其他的都要移除
        highest_priority_bot = sorted_bots[0]
        bots_to_remove_from_group = sorted_bots[1:]

        logger.info(
            f"群 {group_id}: 保留机器人 {highest_priority_bot}，移除 {bots_to_remove_from_group}"
        )

        for bot_id in bots_to_remove_from_group:
            bots_to_remove.append((bot_id, group_id))

    return bots_to_remove


async def batch_remove_bots_from_groups(
    bots_to_remove: list[tuple[int, int]], batch_size: int = 5
) -> tuple[list[tuple[int, int]], list[tuple[int, int, str]]]:
    """批量从群组中移除机器人"""
    success_removals = []
    failed_removals = []

    bots = get_bots()
    total_removals = len(bots_to_remove)

    for i in range(0, total_removals, batch_size):
        batch = bots_to_remove[i : i + batch_size]

        tasks = []
        for bot_id, group_id in batch:
            if str(bot_id) in bots:
                bot = bots[str(bot_id)]
                # 检查是否是OneBot V11适配器
                if hasattr(bot, "set_group_leave"):
                    tasks.append(remove_bot_from_group_safe(bot, group_id, bot_id))
                else:
                    failed_removals.append(
                        (bot_id, group_id, f"机器人 {bot_id} 不支持OneBot V11协议")
                    )
            else:
                failed_removals.append((bot_id, group_id, f"机器人 {bot_id} 不在线"))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for j, ((bot_id, group_id), result) in enumerate(zip(batch, results)):
                if isinstance(result, Exception):
                    failed_removals.append((bot_id, group_id, str(result)))
                elif isinstance(result, tuple) and len(result) == 3:
                    success, message = result[1], result[2]
                    if success:
                        success_removals.append((bot_id, group_id))
                    else:
                        failed_removals.append((bot_id, group_id, message))

        # 输出进度
        completed = min(i + batch_size, total_removals)
        progress = completed / total_removals * 100
        logger.info(f"移除机器人进度: {progress:.1f}% ({completed}/{total_removals})")

        # 批次间延迟
        if i + batch_size < total_removals:
            await asyncio.sleep(1)

    return success_removals, failed_removals


async def remove_bot_from_group_safe(
    bot, group_id: int, bot_id: int
) -> tuple[int, bool, str]:
    """安全地从群组中移除机器人"""
    try:
        await bot.set_group_leave(group_id=group_id)
        return bot_id, True, "成功退出群组"
    except Exception as e:
        logger.warning(f"机器人 {bot_id} 退出群 {group_id} 失败: {e}")
        return bot_id, False, str(e)


# 新增命令：检查重复群组
rdup_check = on_command("checkduplicategroups", permission=SUPERUSER)


@rdup_check.handle()
async def _(bot: Bot):
    await rdup_check.send("🔍 开始检查重复群组...")

    try:
        # 获取所有机器人的群组信息
        all_bot_groups = await get_all_bots_groups()

        if not all_bot_groups:
            await rdup_check.finish("❌ 没有找到任何在线的机器人")

        # 查找重复的群组
        duplicate_groups = await find_duplicate_groups(all_bot_groups)

        if not duplicate_groups:
            await rdup_check.finish("✅ 没有发现重复的群组")

        # 生成报告
        messages = []
        messages.append(f"📊 发现 {len(duplicate_groups)} 个重复群组:")

        for group_id, bot_list in duplicate_groups.items():
            # 获取群组信息
            group_name = "未知"
            member_count = "未知"

            for bot_id in bot_list:
                if bot_id in all_bot_groups:
                    for group in all_bot_groups[bot_id]:
                        if group["group_id"] == group_id:
                            group_name = group["group_name"]
                            member_count = group["member_count"]
                            break
                    break

            # 按优先级排序
            sorted_bots = sorted(
                bot_list, key=lambda x: BOT_PRIORITY.get(x, 0), reverse=True
            )
            highest_priority = sorted_bots[0]
            to_remove = sorted_bots[1:]

            messages.append(f"  群 {group_id} ({group_name}) - 成员: {member_count}")
            messages.append(
                f"    保留: {highest_priority} (优先级: {BOT_PRIORITY.get(highest_priority, 0)})"
            )
            messages.append(f"    移除: {to_remove}")

        # 发送报告
        current_message = ""
        for msg in messages:
            if len(current_message + msg + "\n") > 4000:
                await rdup_check.send(current_message.strip())
                current_message = msg + "\n"
            else:
                current_message += msg + "\n"

        if current_message.strip():
            await rdup_check.send(current_message.strip())

    except FinishedException:
        # finish() 抛出的异常，正常流程，不处理
        raise
    except Exception as e:
        logger.error(f"检查重复群组时发生错误: {e}")
        await rdup_check.send(f"❌ 检查过程中发生错误: {e}")
        return

    await rdup_check.finish("✅ 重复群组检查完成!")


# 新增命令：移除重复群组中的机器人
rdup_remove = on_command("removeduplicategroups", permission=SUPERUSER)


@rdup_remove.handle()
async def _(bot: Bot):
    await rdup_remove.send("🚀 开始移除重复群组中的机器人...")

    try:
        # 获取所有机器人的群组信息
        all_bot_groups = await get_all_bots_groups()

        if not all_bot_groups:
            await rdup_remove.finish("❌ 没有找到任何在线的机器人")

        # 查找重复的群组
        duplicate_groups = await find_duplicate_groups(all_bot_groups)

        if not duplicate_groups:
            await rdup_remove.finish("✅ 没有发现重复的群组")

        # 确定需要移除的机器人
        bots_to_remove = await determine_bots_to_remove(duplicate_groups)

        if not bots_to_remove:
            await rdup_remove.finish("✅ 没有需要移除的机器人")

        await rdup_remove.send(
            f"⚠️ 即将从 {len(duplicate_groups)} 个群组中移除 {len(bots_to_remove)} 个机器人..."
        )

        # 批量移除机器人
        success_removals, failed_removals = await batch_remove_bots_from_groups(
            bots_to_remove
        )

        # 生成结果报告
        messages = []

        if success_removals:
            messages.append(f"✅ 成功移除 ({len(success_removals)} 个):")
            for bot_id, group_id in success_removals[:10]:
                messages.append(f"  ✓ 机器人 {bot_id} 已退出群 {group_id}")
            if len(success_removals) > 10:
                messages.append(f"  ... 还有 {len(success_removals) - 10} 个成功移除")

        if failed_removals:
            messages.append(f"\n❌ 移除失败 ({len(failed_removals)} 个):")
            for bot_id, group_id, error in failed_removals[:10]:
                messages.append(
                    f"  ✗ 机器人 {bot_id} 退出群 {group_id} 失败: {error[:30]}..."
                )
            if len(failed_removals) > 10:
                messages.append(f"  ... 还有 {len(failed_removals) - 10} 个失败")

        # 统计信息
        messages.append(
            f"\n📈 统计: 成功 {len(success_removals)} 个，失败 {len(failed_removals)} 个"
        )

        # 发送结果
        current_message = ""
        for msg in messages:
            if len(current_message + msg + "\n") > 4000:
                await rdup_remove.send(current_message.strip())
                current_message = msg + "\n"
            else:
                current_message += msg + "\n"

        if current_message.strip():
            await rdup_remove.send(current_message.strip())

    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"移除重复群组机器人时发生错误: {e}")
        await rdup_remove.send(f"❌ 移除过程中发生错误: {e}")
        return

    await rdup_remove.finish("🎯 重复群组机器人移除操作完成!")
