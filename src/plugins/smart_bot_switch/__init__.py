import asyncio
import time

from nonebot import get_bots, logger, on_command
from nonebot.adapters.onebot.v11 import ActionFailed, Bot, GroupMessageEvent
from nonebot.message import event_preprocessor, run_postprocessor
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from U1.model import Channel

__plugin_meta__ = PluginMetadata(
    name="智能机器人管理系统",
    description="统一的多机器人智能管理系统，包含活跃监控、故障检测和自动切换",
    usage="""
自动功能：
- 检测机器人活跃状态和故障
- 自动切换失效的assignee
- 故障恢复和负载均衡
- 只在多机器人群组中切换

手动命令：
/bot_status - 查看当前群组机器人状态
/switch_bot <bot_qq> - 切换当前群组的指定机器人 (仅超级用户)
/auto_assign - 自动分配可用机器人到当前群组
/bot_list - 查看所有在线机器人
/bot_health - 查看机器人健康状态和故障信息
/force_switch - 强制切换到当前发送命令的机器人
""",
    type="application",
    homepage="https://github.com/nonebot/nonebot2",
    supported_adapters={"~onebot.v11"},
)

# 配置参数
FAILURE_THRESHOLD = 1  # 连续失败次数阈值
FAILURE_WINDOW = 300  # 5分钟内的失败统计窗口
DISABLE_DURATION = 600  # 失能持续时间 (10分钟)
RECOVERY_CHECK_INTERVAL = 60  # 恢复检查间隔
ACTIVITY_TIMEOUT = 60  # 活跃超时时间

# 全局状态追踪
bot_activity = {}
bot_failures: dict[str, dict] = {}  # bot_id -> {count, last_failure, disabled_until}
failed_actions: dict[str, set[str]] = {}  # bot_id -> set of failed action types

# 缓存机制
_bots_cache = {"data": None, "timestamp": 0, "ttl": 5}  # 5秒缓存
_group_bots_cache = {}  # group_id -> {"data": [...], "timestamp": 0}

# 存储后台任务引用
_auto_switch_task = None
_recovery_task = None
_background_tasks = []


def get_cached_bots():
    """获取缓存的机器人列表"""
    current_time = time.time()
    if (
        _bots_cache["data"] is None
        or current_time - _bots_cache["timestamp"] > _bots_cache["ttl"]
    ):
        _bots_cache["data"] = get_bots()
        _bots_cache["timestamp"] = current_time
    return _bots_cache["data"]


def clear_bots_cache():
    """清除机器人缓存"""
    _bots_cache["data"] = None
    _group_bots_cache.clear()


async def batch_save_channels(channels: list[Channel]) -> int:
    """批量保存频道配置

    Returns:
        int: 成功保存的频道数量
    """
    if not channels:
        return 0

    try:
        # 使用批量更新
        save_tasks = [channel.save() for channel in channels]
        results = await asyncio.gather(*save_tasks, return_exceptions=True)

        success_count = 0
        for result in results:
            if not isinstance(result, Exception):
                success_count += 1
            else:
                logger.error(f"批量保存频道失败: {result}")

        return success_count
    except Exception as e:
        logger.error(f"批量保存频道异常: {e}")
        return 0


def update_bot_activity(bot_id: str):
    """更新机器人活动时间"""
    bot_activity[bot_id] = time.time()


def is_bot_active(bot_id: str, timeout: int = 60) -> bool:
    """检查机器人是否活跃"""
    if bot_id not in bot_activity:
        return False
    return (time.time() - bot_activity[bot_id]) < timeout


async def get_best_bot_from_candidates(
    candidates: list[str], exclude_bot: str | None = None
) -> tuple[str | None, int]:
    """从候选机器人中选择最佳的机器人

    Returns:
        tuple: (best_bot_id, priority) 如果没有找到返回 (None, 0)
    """
    if not candidates:
        return None, 0

    available_bots = get_cached_bots()
    scored_candidates = []

    for bot_id in candidates:
        if bot_id == exclude_bot:
            continue

        # 检查机器人是否在线
        if bot_id not in available_bots:
            continue

        # 检查是否被故障监控禁用 - 被禁用的机器人直接跳过
        is_disabled = BotFailureMonitor.is_bot_disabled(bot_id)
        if is_disabled:
            logger.debug(f"跳过被禁用的机器人: {bot_id}")
            continue

        # 检查是否活跃
        is_active = is_bot_active(bot_id)

        # 获取故障状态信息
        bot_status = BotFailureMonitor.get_bot_status(bot_id)
        failure_count = bot_status.get("failures", 0)

        # 计算优先级（只考虑健康的机器人）
        priority = 0
        if is_active and failure_count == 0:
            priority = 4  # 最高优先级：活跃且无故障历史
        elif is_active and failure_count < 3:
            priority = 3  # 高优先级：活跃但有少量故障历史
        elif failure_count == 0:
            priority = 2  # 中等优先级：无故障但可能不够活跃
        elif failure_count < 5:
            priority = 1  # 低优先级：有一定故障历史但还可用
        # 故障次数过多的机器人优先级为0，不会被选择

        if priority > 0:  # 只添加有效的候选者
            scored_candidates.append((bot_id, priority))
            logger.debug(
                f"候选机器人 {bot_id}: 优先级={priority}, 活跃={is_active}, 故障数={failure_count}"
            )

    if not scored_candidates:
        logger.warning(
            f"从候选列表 {candidates} 中未找到可用机器人 (排除: {exclude_bot})"
        )
        return None, 0

    # 按优先级排序，选择最佳候选者
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    best_bot, best_priority = scored_candidates[0]
    logger.info(f"选择最佳机器人: {best_bot} (优先级: {best_priority})")
    return best_bot, best_priority


async def smart_assign_bot(channel: Channel, current_bot_id: str) -> str:
    """智能分配机器人"""
    # 获取该群组中的所有机器人
    group_bots = await get_bots_in_group(channel.guildId)

    # 如果群里只有一个机器人或没有其他机器人，不进行切换
    if len(group_bots) <= 1:
        logger.info(
            f"群组 {channel.guildId} 只有 {len(group_bots)} 个机器人，不进行自动切换"
        )
        return channel.assignee if channel.assignee else current_bot_id

    logger.info(f"群组 {channel.guildId} 有 {len(group_bots)} 个机器人: {group_bots}")

    # 检查当前assignee是否仍然有效
    current_assignee = channel.assignee
    exclude_bot = None

    if current_assignee:
        # 如果当前assignee被禁用或离线，需要排除它
        is_disabled = BotFailureMonitor.is_bot_disabled(current_assignee)
        available_bots = get_cached_bots()
        is_offline = current_assignee not in available_bots

        if is_disabled or is_offline:
            exclude_bot = current_assignee
            logger.info(
                f"当前assignee {current_assignee} 已失效 (禁用: {is_disabled}, 离线: {is_offline})，需要切换"
            )

    # 使用公共函数选择最佳机器人
    best_bot, priority = await get_best_bot_from_candidates(
        group_bots, exclude_bot=exclude_bot
    )

    if best_bot and best_bot != channel.assignee:
        old_assignee = channel.assignee
        channel.assignee = best_bot
        await channel.save()
        logger.info(
            f"智能切换群组 {channel.guildId} 的机器人从 {old_assignee} 到 {best_bot} (优先级: {priority})"
        )
        return best_bot
    elif best_bot:
        logger.info(f"群组 {channel.guildId} 当前assignee {best_bot} 仍为最佳选择")
        return best_bot
    else:
        logger.warning(f"群组 {channel.guildId} 无法找到可用的机器人，保持当前assignee")
        return channel.assignee if channel.assignee else current_bot_id


# 定期检查和自动切换任务
async def auto_switch_task():
    """定期检查是否需要自动切换机器人（并发优化）"""
    # 启动时等待机器人连接完成
    await asyncio.sleep(10)  # 等待10秒让bot连接
    logger.info("开始执行自动切换任务监控")

    while True:
        try:
            # 清除缓存，确保获取最新状态
            clear_bots_cache()

            # 获取所有频道和可用机器人
            channels = await Channel.all()
            available_bots = get_cached_bots()

            # 如果没有任何机器人在线，跳过本轮检查
            if not available_bots:
                await asyncio.sleep(30)
                continue

            # 预筛选需要切换的群组
            switch_candidates = []
            for channel in channels:
                if not channel.assignee:
                    continue

                # 检查当前assignee是否还有效
                needs_switch = False
                reason = ""

                if channel.assignee not in available_bots:
                    needs_switch = True
                    reason = "不在线"
                elif not is_bot_active(channel.assignee, timeout=300):  # 5分钟无活动
                    needs_switch = True
                    reason = "长时间无活动"
                elif BotFailureMonitor.is_bot_disabled(channel.assignee):
                    needs_switch = True
                    reason = "已被故障监控禁用"

                if needs_switch:
                    logger.warning(
                        f"群组 {channel.guildId} 的assignee {channel.assignee} {reason}"
                    )
                    # 额外检查：确保有可用的替代机器人再添加到切换候选列表
                    group_bots = await get_bots_in_group(channel.guildId)
                    if len(group_bots) > 1:  # 只有在有多个机器人时才考虑切换
                        switch_candidates.append(channel)
                    else:
                        logger.info(
                            f"群组 {channel.guildId} 只有一个机器人，跳过自动切换"
                        )

            if not switch_candidates:
                await asyncio.sleep(30)
                continue

            # 限制并发数量，避免过载
            batch_size = min(10, len(switch_candidates))  # 最多同时处理10个群组

            for i in range(0, len(switch_candidates), batch_size):
                batch = switch_candidates[i : i + batch_size]

                # 批量执行切换任务
                switch_tasks = [
                    smart_assign_bot(channel, channel.assignee) for channel in batch
                ]

                results = await asyncio.gather(*switch_tasks, return_exceptions=True)

                # 统计结果
                success_count = 0
                error_count = 0
                for result in results:
                    if isinstance(result, Exception):
                        error_count += 1
                        logger.error(f"智能切换失败: {result}")
                    else:
                        success_count += 1

                if success_count > 0 or error_count > 0:
                    logger.info(
                        f"批次切换完成: 成功 {success_count}，失败 {error_count}"
                    )

                # 批次间短暂延迟，避免过载
                if i + batch_size < len(switch_candidates):
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"自动切换任务异常: {e}")

        await asyncio.sleep(30)  # 每30秒检查一次


# 启动自动切换任务
from nonebot import get_driver

driver = get_driver()
_auto_switch_task = None


@driver.on_startup
async def start_auto_switch():
    global _auto_switch_task, _recovery_task
    _auto_switch_task = asyncio.create_task(auto_switch_task())
    _recovery_task = asyncio.create_task(recovery_task())
    logger.info("智能机器人管理系统已启动 (将在延迟后开始监控)")


# 定期恢复检查任务
async def recovery_task():
    """定期检查和恢复故障机器人"""
    # 启动时等待机器人连接完成
    await asyncio.sleep(15)  # 等待15秒让bot连接，比auto_switch_task稍晚启动
    logger.info("开始执行故障恢复任务监控")

    while True:
        try:
            available_bots = get_cached_bots()
            # 如果没有任何机器人在线，跳过本轮检查
            if available_bots:
                await BotFailureMonitor.check_recovery()
        except Exception as e:
            logger.error(f"恢复检查任务异常: {e}")

        await asyncio.sleep(RECOVERY_CHECK_INTERVAL)


# 启动恢复检查任务
@driver.on_startup
async def start_recovery_task():
    # 这个函数现在是空的，因为recovery_task已经在start_auto_switch中启动了
    pass


# 手动管理命令
bot_status_cmd = on_command("bot_status", aliases={"机器人状态"}, priority=5)


@bot_status_cmd.handle()
async def handle_bot_status(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)

    group_id = str(event.group_id)
    channel = await Channel.get_or_none(guildId=group_id)

    if not channel:
        await bot_status_cmd.finish("未找到群组频道配置")

    available_bots = get_cached_bots()
    msg_parts = [f"群组 {group_id} 机器人状态：\n"]

    # 当前指定机器人
    if channel.assignee:
        status = (
            "在线"
            if channel.assignee in available_bots and is_bot_active(channel.assignee)
            else "离线"
        )
        msg_parts.append(f"📌 当前指定机器人: {channel.assignee} ({status})")
    else:
        msg_parts.append("📌 当前指定机器人: 无")

    msg_parts.append("\n可用机器人列表:")

    for bot_id, _ in available_bots.items():
        is_current = "✅" if bot_id == channel.assignee else "⭕"
        activity_status = "活跃" if is_bot_active(bot_id) else "空闲"
        msg_parts.append(f"{is_current} {bot_id} ({activity_status})")

    await bot_status_cmd.finish("\n".join(msg_parts))


# 强制切换到当前机器人
force_switch_cmd = on_command("force_switch", aliases={"强制切换"}, priority=5)


@force_switch_cmd.handle()
async def handle_force_switch(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)

    group_id = str(event.group_id)
    channel = await Channel.get_or_none(guildId=group_id)

    if not channel:
        await force_switch_cmd.finish("未找到群组频道配置")

    old_assignee = channel.assignee
    channel.assignee = bot.self_id
    await channel.save()

    logger.info(f"强制切换群组 {group_id} 的机器人从 {old_assignee} 到 {bot.self_id}")
    await force_switch_cmd.finish(f"✅ 已强制切换到当前机器人: {bot.self_id}")


# 其他命令继续使用之前bot_manager中的实现，这里不重复了
switch_bot_cmd = on_command(
    "switch_bot", aliases={"切换机器人"}, permission=SUPERUSER, priority=5
)


@switch_bot_cmd.handle()
async def handle_switch_bot(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)

    group_id = str(event.group_id)
    channel = await Channel.get_or_none(guildId=group_id)

    if not channel:
        await switch_bot_cmd.finish("未找到群组频道配置")

    args = str(event.get_message()).strip().split()
    if len(args) < 2:
        await switch_bot_cmd.finish(
            "请指定要切换的机器人QQ号\n用法: /switch_bot <bot_qq>"
        )

    target_bot_id = args[1]
    available_bots = get_cached_bots()

    if target_bot_id not in available_bots:
        await switch_bot_cmd.finish(f"机器人 {target_bot_id} 不在线或不可用")

    old_assignee = channel.assignee
    channel.assignee = target_bot_id
    await channel.save()

    logger.info(f"手动切换群组 {group_id} 的机器人从 {old_assignee} 到 {target_bot_id}")
    await switch_bot_cmd.finish(
        f"✅ 已将群组机器人从 {old_assignee} 切换到 {target_bot_id}"
    )


auto_assign_cmd = on_command("auto_assign", aliases={"自动分配"}, priority=5)


@auto_assign_cmd.handle()
async def handle_auto_assign(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)

    group_id = str(event.group_id)
    channel = await Channel.get_or_none(guildId=group_id)

    if not channel:
        await auto_assign_cmd.finish("未找到群组频道配置")

    best_bot = await smart_assign_bot(channel, bot.self_id)
    await auto_assign_cmd.finish(f"✅ 已智能分配机器人: {best_bot}")


async def check_bot_in_group(bot_id: str, group_id: str) -> bool:
    """检查机器人是否在指定群组中"""
    try:
        available_bots = get_cached_bots()
        if bot_id not in available_bots:
            return False

        bot = available_bots[bot_id]

        # 尝试获取群信息来验证机器人是否在群里
        try:
            await bot.get_group_info(group_id=int(group_id))
            return True
        except Exception:
            # 如果无法获取群信息，可能机器人不在群里或权限不足
            return False

    except Exception as e:
        logger.warning(f"检查机器人 {bot_id} 是否在群 {group_id} 时出错: {e}")
        return False


async def check_bots_in_group_batch(bot_ids: list[str], group_id: str) -> list[str]:
    """并发检查多个机器人是否在指定群组中

    Returns:
        list[str]: 在群组中的机器人ID列表
    """
    if not bot_ids:
        return []

    # 并发检查所有机器人
    check_tasks = [check_bot_in_group(bot_id, group_id) for bot_id in bot_ids]
    results = await asyncio.gather(*check_tasks, return_exceptions=True)

    # 收集在群组中的机器人
    bots_in_group = []
    for bot_id, result in zip(bot_ids, results):
        if isinstance(result, bool) and result:
            bots_in_group.append(bot_id)
        elif isinstance(result, Exception):
            logger.warning(f"检查机器人 {bot_id} 时发生异常: {result}")

    return bots_in_group


async def get_bots_in_group(group_id: str) -> list[str]:
    """获取指定群组中的所有机器人（带缓存和并发优化）"""
    current_time = time.time()
    cache_ttl = 30  # 30秒缓存

    # 检查缓存
    if group_id in _group_bots_cache:
        cache_entry = _group_bots_cache[group_id]
        if current_time - cache_entry["timestamp"] < cache_ttl:
            return cache_entry["data"]

    # 缓存过期或不存在，重新获取
    available_bots = get_cached_bots()
    bot_ids = list(available_bots.keys())

    # 使用并发批量检查
    bots_in_group = await check_bots_in_group_batch(bot_ids, group_id)

    # 更新缓存
    _group_bots_cache[group_id] = {"data": bots_in_group, "timestamp": current_time}

    return bots_in_group


class BotFailureMonitor:
    """机器人故障监控和自动恢复"""

    @staticmethod
    async def validate_bot_health(bot_id: str) -> tuple[bool, str]:
        """验证机器人健康状态

        Returns:
            tuple: (is_healthy, error_message)
        """
        try:
            # 检查是否在线
            available_bots = get_cached_bots()
            if bot_id not in available_bots:
                return False, "机器人离线"

            # 检查是否被禁用
            if BotFailureMonitor.is_bot_disabled(bot_id):
                return False, "机器人被故障监控禁用"

            # 检查故障状态
            status_info = BotFailureMonitor.get_bot_status(bot_id)
            if status_info["status"] == "disabled":
                return False, "机器人处于禁用状态"

            # 尝试简单的API调用测试
            bot = available_bots[bot_id]
            await bot.get_login_info()

            return True, "健康"

        except Exception as e:
            return False, f"健康检查失败: {e!s}"

    @staticmethod
    def record_failure(bot_id: str, action_type: str = "unknown", error: str = ""):
        """记录机器人故障"""
        current_time = time.time()

        if bot_id not in bot_failures:
            bot_failures[bot_id] = {
                "count": 0,
                "last_failure": 0,
                "disabled_until": 0,
                "errors": [],
            }

        if bot_id not in failed_actions:
            failed_actions[bot_id] = set()

        # 清理过期的故障记录
        if current_time - bot_failures[bot_id]["last_failure"] > FAILURE_WINDOW:
            bot_failures[bot_id]["count"] = 0
            failed_actions[bot_id].clear()

        # 记录新的故障
        bot_failures[bot_id]["count"] += 1
        bot_failures[bot_id]["last_failure"] = current_time
        bot_failures[bot_id]["errors"].append(
            {"time": current_time, "action": action_type, "error": error}
        )
        failed_actions[bot_id].add(action_type)

        logger.warning(f"机器人 {bot_id} 发生故障: {action_type} - {error}")

        # 记录详细的故障信息用于调试
        logger.debug(
            f"故障详情 - 机器人: {bot_id}, 类型: {action_type}, "
            f"当前故障数: {bot_failures[bot_id]['count']}, "
            f"阈值: {FAILURE_THRESHOLD}"
        )

        # 检查是否需要临时禁用
        if bot_failures[bot_id]["count"] >= FAILURE_THRESHOLD:
            bot_failures[bot_id]["disabled_until"] = current_time + DISABLE_DURATION
            logger.error(
                f"机器人 {bot_id} 故障次数过多，临时禁用 {DISABLE_DURATION / 60:.1f} 分钟"
            )

            # 尝试自动切换其他机器人
            task = asyncio.create_task(BotFailureMonitor.auto_failover(bot_id))
            _background_tasks.append(task)

    @staticmethod
    def is_bot_disabled(bot_id: str) -> bool:
        """检查机器人是否被临时禁用"""
        if bot_id not in bot_failures:
            return False

        current_time = time.time()
        disabled_until = bot_failures[bot_id].get("disabled_until", 0)

        return current_time < disabled_until

    @staticmethod
    async def process_failover_for_channel(channel: Channel, failed_bot_id: str):
        """为单个频道处理故障转移"""
        try:
            group_id = channel.guildId

            # 获取该群组中的所有机器人
            bots_in_group = await get_bots_in_group(group_id)

            # 如果群里只有故障机器人一个或没有其他机器人，则不进行切换
            if len(bots_in_group) <= 1:
                logger.info(
                    f"群组 {group_id} 只有 {len(bots_in_group)} 个机器人，跳过故障转移"
                )
                return

            # 使用公共函数选择备用机器人，明确排除故障机器人
            backup_bot, priority = await get_best_bot_from_candidates(
                bots_in_group, exclude_bot=failed_bot_id
            )

            if not backup_bot:
                available_bots = get_cached_bots()
                disabled_bots = [
                    bot_id
                    for bot_id in bots_in_group
                    if BotFailureMonitor.is_bot_disabled(bot_id)
                ]
                offline_bots = [
                    bot_id for bot_id in bots_in_group if bot_id not in available_bots
                ]
                logger.warning(
                    f"群组 {group_id} 内无法找到可用的备用机器人 "
                    f"(群内机器人: {bots_in_group}, 禁用: {disabled_bots}, 离线: {offline_bots}, 故障: {failed_bot_id})"
                )
                return

            # 额外的健康检查：确保选中的机器人真的可用
            is_healthy, health_msg = await BotFailureMonitor.validate_bot_health(
                backup_bot
            )
            if not is_healthy:
                logger.error(
                    f"选中的备用机器人 {backup_bot} 健康检查失败: {health_msg}"
                )
                return

            old_assignee = channel.assignee
            channel.assignee = backup_bot
            await channel.save()
            logger.info(
                f"故障转移: 群组 {channel.guildId} 从 {old_assignee} 切换到 {backup_bot} "
                f"(优先级: {priority}, 群内有{len(bots_in_group)}个机器人)"
            )

        except Exception as e:
            logger.error(f"群组 {channel.guildId} 故障转移失败: {e}")

    @staticmethod
    async def auto_failover(failed_bot_id: str):
        """自动故障转移（并发优化）"""
        try:
            # 查找所有使用该机器人的群组
            channels = await Channel.filter(assignee=failed_bot_id)

            if not channels:
                return

            # 并发处理所有群组的故障转移
            failover_tasks = [
                BotFailureMonitor.process_failover_for_channel(channel, failed_bot_id)
                for channel in channels
            ]

            # 使用gather并处理异常
            results = await asyncio.gather(*failover_tasks, return_exceptions=True)

            # 统计处理结果
            success_count = 0
            error_count = 0
            for result in results:
                if isinstance(result, Exception):
                    error_count += 1
                else:
                    success_count += 1

            if error_count > 0:
                logger.warning(
                    f"故障转移完成: 成功 {success_count} 个群组，失败 {error_count} 个群组"
                )
            else:
                logger.info(f"故障转移完成: 成功处理 {success_count} 个群组")

        except Exception as e:
            logger.error(f"自动故障转移失败: {e}")

    @staticmethod
    async def check_bot_recovery(
        bot_id: str, available_bots: dict
    ) -> tuple[str, bool, str]:
        """检查单个机器人的恢复状态

        Returns:
            tuple: (bot_id, is_recovered, error_message)
        """
        try:
            current_time = time.time()
            failure_info = bot_failures[bot_id]

            # 检查是否到达恢复时间
            if current_time >= failure_info.get("disabled_until", 0):
                if failure_info.get("disabled_until", 0) > 0:  # 之前被禁用过
                    # 尝试简单的健康检查
                    bot = available_bots[bot_id]
                    await bot.get_login_info()
                    return bot_id, True, ""

            return bot_id, False, "未到恢复时间"
        except Exception as e:
            return bot_id, False, str(e)

    @staticmethod
    async def check_recovery():
        """检查故障机器人是否已恢复（并发优化）"""
        current_time = time.time()
        available_bots = get_cached_bots()

        # 收集需要检查的机器人
        bots_to_check = []
        for bot_id in list(bot_failures.keys()):
            if bot_id in available_bots:
                failure_info = bot_failures[bot_id]
                # 只检查可能需要恢复的机器人
                if current_time >= failure_info.get("disabled_until", 0):
                    if failure_info.get("disabled_until", 0) > 0:  # 之前被禁用过
                        bots_to_check.append(bot_id)

        if not bots_to_check:
            return

        logger.info(f"并发检查 {len(bots_to_check)} 个机器人的恢复状态")

        # 并发检查所有机器人的恢复状态
        recovery_tasks = [
            BotFailureMonitor.check_bot_recovery(bot_id, available_bots)
            for bot_id in bots_to_check
        ]

        results = await asyncio.gather(*recovery_tasks, return_exceptions=True)

        # 处理检查结果
        recovered_count = 0
        failed_count = 0

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"恢复检查异常: {result}")
                continue

            if not isinstance(result, tuple) or len(result) != 3:
                logger.error(f"恢复检查返回格式错误: {result}")
                continue

            bot_id, is_recovered, error_msg = result

            if is_recovered:
                # 恢复成功，清理故障记录
                bot_failures[bot_id] = {
                    "count": 0,
                    "last_failure": 0,
                    "disabled_until": 0,
                    "errors": [],
                }
                if bot_id in failed_actions:
                    failed_actions[bot_id].clear()

                logger.info(f"机器人 {bot_id} 已成功恢复")
                recovered_count += 1
            else:
                # 延长禁用时间
                if bot_id in bot_failures:
                    bot_failures[bot_id]["disabled_until"] = (
                        current_time + DISABLE_DURATION
                    )
                    logger.warning(
                        f"机器人 {bot_id} 恢复检查失败，延长禁用时间: {error_msg}"
                    )
                    failed_count += 1

        if recovered_count > 0 or failed_count > 0:
            logger.info(
                f"恢复检查完成: 恢复 {recovered_count} 个，失败 {failed_count} 个"
            )

    @staticmethod
    def get_bot_status(bot_id: str) -> dict:
        """获取机器人状态信息"""
        if bot_id not in bot_failures:
            return {"status": "healthy", "failures": 0}

        failure_info = bot_failures[bot_id]
        current_time = time.time()

        if current_time < failure_info.get("disabled_until", 0):
            remaining = failure_info["disabled_until"] - current_time
            return {
                "status": "disabled",
                "failures": failure_info["count"],
                "disabled_remaining": remaining,
                "failed_actions": list(failed_actions.get(bot_id, set())),
            }
        elif failure_info["count"] > 0:
            return {
                "status": "recovering",
                "failures": failure_info["count"],
                "failed_actions": list(failed_actions.get(bot_id, set())),
            }
        else:
            return {"status": "healthy", "failures": 0}


# 故障捕获装饰器
@run_postprocessor
async def handle_action_failed(
    matcher,
    exception: Exception | None,
    bot: Bot,
    event: GroupMessageEvent,
    state,
):
    if exception and isinstance(exception, ActionFailed):
        action_type = getattr(exception, "action_type", "unknown")
        error_msg = str(exception)
        BotFailureMonitor.record_failure(bot.self_id, action_type, error_msg)


# 在事件预处理中更新活动状态
@event_preprocessor
async def track_bot_activity(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)


# 查看机器人健康状态
bot_health_cmd = on_command(
    "bot_health", aliases={"机器人健康", "故障状态"}, priority=5
)


@bot_health_cmd.handle()
async def handle_bot_health(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)

    available_bots = get_cached_bots()
    msg_parts = ["🏥 机器人健康状态报告:\n"]

    for bot_id, _ in available_bots.items():
        status_info = BotFailureMonitor.get_bot_status(bot_id)
        status = status_info["status"]
        failures = status_info["failures"]

        if status == "healthy":
            status_emoji = "✅"
            status_text = "健康"
        elif status == "recovering":
            status_emoji = "🟡"
            status_text = f"恢复中 (故障{failures}次)"
        elif status == "disabled":
            status_emoji = "🔴"
            remaining = status_info.get("disabled_remaining", 0)
            status_text = f"已禁用 (剩余{remaining / 60:.1f}分钟)"
        else:
            status_emoji = "❓"
            status_text = "未知"

        msg_parts.append(f"{status_emoji} {bot_id}: {status_text}")

        # 显示失败的操作类型
        failed_actions_list = status_info.get("failed_actions", [])
        if failed_actions_list:
            failed_actions_str = ", ".join(failed_actions_list)
            msg_parts.append(f"   └ 失败操作: {failed_actions_str}")

    if len(msg_parts) == 1:
        msg_parts.append("暂无机器人在线")

    await bot_health_cmd.finish("\n".join(msg_parts))
