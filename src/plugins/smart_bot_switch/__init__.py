import asyncio
import time

from cachetools import TTLCache
from nonebot import get_bots, logger, on_command
from nonebot.adapters.onebot.v11 import ActionFailed, Bot, GroupMessageEvent
from nonebot.internal.matcher.matcher import Matcher
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

# 性能配置常量
FAILURE_THRESHOLD = 1  # 连续失败次数阈值
FAILURE_WINDOW = 300  # 5分钟内的失败统计窗口
DISABLE_DURATION = 600  # 失能持续时间 (10分钟)
RECOVERY_CHECK_INTERVAL = 60  # 恢复检查间隔
ACTIVITY_TIMEOUT = 60  # 活跃超时时间
AUTO_SWITCH_INTERVAL = 45  # 自动切换检查间隔（秒）
RECOVERY_INTERVAL = 60  # 恢复检查间隔（秒）
MAX_CONCURRENT_SWITCHES = 8  # 最大并发切换数量
BATCH_PROCESS_DELAY = 1.5  # 批处理间延迟（秒）

# 全局状态变量
bot_activity = {}
bot_failures: dict[str, dict] = {}  # bot_id -> {count, last_failure, disabled_until}
failed_actions: dict[str, set[str]] = {}  # bot_id -> set of failed action types
_bots_cache = {"data": None, "timestamp": 0, "ttl": 3}  # 减少到3秒，更快响应
_group_bots_cache = TTLCache(maxsize=1000, ttl=180)  # 增加到3分钟，减少频繁查询
_non_switchable_groups_cache = TTLCache(
    maxsize=500, ttl=900
)  # 增加到15分钟，减少重复检查
_short_term_non_switchable_cache = TTLCache(
    maxsize=200, ttl=180
)  # 短期缓存减少到3分钟，更快重试
_long_term_non_switchable_cache = TTLCache(
    maxsize=300, ttl=3600
)  # 长期缓存增加到1小时，稳定状态持续更久
_auto_switch_task = None
_recovery_task = None
_background_tasks = []

# 并发控制
_concurrent_operations = {"switches": 0, "recoveries": 0, "failovers": 0}
_operation_limits = {
    "switches": MAX_CONCURRENT_SWITCHES,
    "recoveries": 4,
    "failovers": 6,
}


class ConcurrencyLimiter:
    """并发操作限制器"""

    @staticmethod
    async def acquire(operation_type: str) -> bool:
        """尝试获取操作许可"""
        if operation_type not in _concurrent_operations:
            return True

        current = _concurrent_operations[operation_type]
        limit = _operation_limits.get(operation_type, 10)

        if current >= limit:
            logger.debug(f"并发限制: {operation_type} 已达上限 {limit}")
            return False

        _concurrent_operations[operation_type] += 1
        return True

    @staticmethod
    def release(operation_type: str):
        """释放操作许可"""
        if operation_type in _concurrent_operations:
            _concurrent_operations[operation_type] = max(
                0, _concurrent_operations[operation_type] - 1
            )

    @staticmethod
    def get_stats() -> dict:
        """获取并发统计信息"""
        return _concurrent_operations.copy()


async def yield_control():
    """主动让出控制权给其他协程"""
    await asyncio.sleep(0.001)  # 1ms的短暂让出


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


def is_group_non_switchable_cached(group_id: str) -> tuple[bool, str]:
    """检查群组是否在无法切换的缓存中

    Returns:
        tuple: (is_cached, reason)
    """
    for cache_name, cache in [
        ("短期", _short_term_non_switchable_cache),
        ("默认", _non_switchable_groups_cache),
        ("长期", _long_term_non_switchable_cache),
    ]:
        reason = cache.get(group_id)
        if reason is not None:
            logger.debug(f"命中{cache_name}无法切换缓存: {group_id} - {reason}")
            return True, reason

    return False, ""


def cache_non_switchable_group(group_id: str, reason: str, ttl: int = 900):
    """缓存无法切换的群组

    Args:
        group_id: 群组ID
        reason: 无法切换的原因
        ttl: 缓存存活时间（秒），根据TTL选择合适的缓存实例
    """
    if ttl <= 180:  # 3分钟以内使用短期缓存
        cache = _short_term_non_switchable_cache
        cache_type = "短期"
    elif ttl >= 3600:  # 1小时以上使用长期缓存
        cache = _long_term_non_switchable_cache
        cache_type = "长期"
    else:  # 默认使用标准缓存
        cache = _non_switchable_groups_cache
        cache_type = "默认"

    cache[group_id] = reason
    logger.debug(
        f"缓存无法切换群组到{cache_type}缓存: {group_id}, 原因: {reason}, TTL: {ttl}秒"
    )


async def batch_save_channels(channels: list[Channel]) -> int:
    """批量保存频道配置

    Returns:
        int: 成功保存的频道数量
    """
    if not channels:
        return 0

    try:
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
    candidates: list[str],
    exclude_bot: str | None = None,
    current_bot_id: str | None = None,
) -> tuple[str | None, int]:
    """从候选机器人中选择最佳的机器人

    Args:
        candidates: 候选机器人ID列表
        exclude_bot: 要排除的机器人ID
        current_bot_id: 当前正在使用的机器人ID，如果其优先级不低于其他候选者则继续使用

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
        if bot_id not in available_bots:
            continue
        is_disabled = BotFailureMonitor.is_bot_disabled(bot_id)
        if is_disabled:
            logger.debug(f"跳过被禁用的机器人: {bot_id}")
            continue
        is_active = is_bot_active(bot_id)
        bot_status = BotFailureMonitor.get_bot_status(bot_id)
        failure_count = bot_status.get("failures", 0)
        priority = 0
        if is_active and failure_count == 0:
            priority = 4  # 最高优先级：活跃且无故障历史
        elif is_active and failure_count < 3:
            priority = 3  # 高优先级：活跃但有少量故障历史
        elif failure_count == 0:
            priority = 2  # 中等优先级：无故障但可能不够活跃
        elif failure_count < 2:
            priority = 1  # 低优先级：有一定故障历史但还可用

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

    # 按优先级排序
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    highest_priority = scored_candidates[0][1]

    if current_bot_id:
        for bot_id, priority in scored_candidates:
            if bot_id == current_bot_id and priority == highest_priority:
                logger.info(
                    f"继续使用当前机器人: {current_bot_id} (优先级: {priority})"
                )
                return current_bot_id, priority

    best_bot, best_priority = scored_candidates[0]
    logger.info(f"选择最佳机器人: {best_bot} (优先级: {best_priority})")
    return best_bot, best_priority


async def smart_assign_bot(channel: Channel, current_bot_id: str) -> str:
    """智能分配机器人"""
    # 并发控制
    if not await ConcurrencyLimiter.acquire("switches"):
        logger.debug(f"群组 {channel.guildId} 切换被并发限制跳过")
        return channel.assignee if channel.assignee else current_bot_id

    try:
        group_id = channel.guildId
        is_cached, cached_reason = is_group_non_switchable_cached(group_id)
        if is_cached:
            logger.debug(f"群组 {group_id} 在无法切换缓存中: {cached_reason}")
            return channel.assignee if channel.assignee else current_bot_id

        # 主动让出控制权
        await yield_control()

        group_bots = await get_bots_in_group(group_id)
        if len(group_bots) <= 1:
            reason = f"只有{len(group_bots)}个机器人"
            cache_non_switchable_group(group_id, reason, ttl=3600)  # 1小时缓存
            return channel.assignee if channel.assignee else current_bot_id

        logger.debug(f"群组 {group_id} 有 {len(group_bots)} 个机器人: {group_bots}")
        current_assignee = channel.assignee
        exclude_bot = None

        if current_assignee:
            is_disabled = BotFailureMonitor.is_bot_disabled(current_assignee)
            available_bots = get_cached_bots()
            is_offline = current_assignee not in available_bots

            if is_disabled or is_offline:
                exclude_bot = current_assignee
                logger.debug(
                    f"当前assignee {current_assignee} 已失效 (禁用: {is_disabled}, 离线: {is_offline})，需要切换"
                )

        # 再次让出控制权
        await yield_control()

        best_bot, priority = await get_best_bot_from_candidates(
            group_bots, exclude_bot=exclude_bot, current_bot_id=channel.assignee
        )

        if best_bot and best_bot != channel.assignee:
            old_assignee = channel.assignee
            channel.assignee = best_bot
            await channel.save()
            logger.info(
                f"智能切换群组 {group_id} 的机器人从 {old_assignee} 到 {best_bot} (优先级: {priority})"
            )
            return best_bot
        elif best_bot:
            logger.debug(f"群组 {group_id} 当前assignee {best_bot} 仍为最佳选择")
            return best_bot
        else:
            reason = "无可用机器人"
            logger.warning(f"群组 {group_id} {reason}，保持当前assignee")
            cache_non_switchable_group(group_id, reason, ttl=180)  # 3分钟缓存，更快重试
            return channel.assignee if channel.assignee else current_bot_id

    finally:
        ConcurrencyLimiter.release("switches")


async def auto_switch_task():
    """定期检查是否需要自动切换机器人"""
    await asyncio.sleep(5)
    logger.info("开始执行自动切换任务监控")

    last_check_time = 0

    while True:
        try:
            current_time = time.time()

            # 智能调整检查间隔
            time_since_last = current_time - last_check_time
            if time_since_last < AUTO_SWITCH_INTERVAL:
                await asyncio.sleep(AUTO_SWITCH_INTERVAL - time_since_last)
                continue

            last_check_time = current_time

            # 清理后台任务，但不要每次都清理
            if len(_background_tasks) > 10:
                cleanup_background_tasks()

            # 更新缓存（如果需要）
            if (
                _bots_cache["data"] is None
                or current_time - _bots_cache["timestamp"] > _bots_cache["ttl"]
            ):
                clear_bots_cache()

            available_bots = get_cached_bots()
            if not available_bots:
                await asyncio.sleep(30)  # 无机器人时延长等待
                continue

            channels = await Channel.filter(assignee__isnull=False)
            if not channels:
                await asyncio.sleep(AUTO_SWITCH_INTERVAL)
                continue

            switch_candidates = []
            cached_skip_count = 0

            for channel in channels:
                group_id = channel.guildId
                is_cached, cached_reason = is_group_non_switchable_cached(group_id)
                if is_cached:
                    cached_skip_count += 1
                    logger.debug(f"跳过缓存的无法切换群组 {group_id}: {cached_reason}")
                    continue

                needs_switch = False
                reason = ""

                if channel.assignee not in available_bots:
                    needs_switch = True
                    reason = "不在线"
                elif not is_bot_active(
                    channel.assignee,
                    timeout=240,  # 减少误判
                ):
                    needs_switch = True
                    reason = "长时间无活动"
                elif BotFailureMonitor.is_bot_disabled(channel.assignee):
                    needs_switch = True
                    reason = "已被故障监控禁用"

                if needs_switch:
                    logger.debug(
                        f"群组 {group_id} 的assignee {channel.assignee} {reason}"
                    )
                    switch_candidates.append((channel, reason))

            total_groups = len(channels)
            need_switch_count = len(switch_candidates)

            if cached_skip_count > 0:
                logger.debug(f"跳过 {cached_skip_count} 个缓存的无法切换群组")

            if not switch_candidates:
                if total_groups > 0:
                    logger.debug(f"检查了 {total_groups} 个群组，无需切换")
                await asyncio.sleep(AUTO_SWITCH_INTERVAL)
                continue

            logger.info(f"发现 {need_switch_count} 个群组需要切换机器人")

            batch_size = min(MAX_CONCURRENT_SWITCHES, need_switch_count)

            total_success = 0
            total_errors = 0

            for i in range(0, need_switch_count, batch_size):
                batch = switch_candidates[i : i + batch_size]
                batch_channels = [item[0] for item in batch]
                batch_reasons = [item[1] for item in batch]

                switch_tasks = [
                    smart_assign_bot(channel, channel.assignee)
                    for channel in batch_channels
                ]

                results = await asyncio.gather(*switch_tasks, return_exceptions=True)
                success_count = 0
                error_count = 0
                successful_switches = []

                for j, (result, channel, reason) in enumerate(
                    zip(results, batch_channels, batch_reasons)
                ):
                    if isinstance(result, Exception):
                        error_count += 1
                        logger.error(f"群组 {channel.guildId} 智能切换失败: {result}")
                    else:
                        success_count += 1
                        if result != channel.assignee:  # 实际发生了切换
                            successful_switches.append(f"{channel.guildId}({reason})")

                if successful_switches:
                    logger.info(
                        f"批次切换成功 {len(successful_switches)} 个: {', '.join(successful_switches[:3])}"
                    )
                    if len(successful_switches) > 3:
                        logger.info(
                            f"... 还有 {len(successful_switches) - 3} 个群组成功切换"
                        )

                if error_count > 0:
                    logger.warning(f"批次中有 {error_count} 个群组切换失败")

                total_success += success_count
                total_errors += error_count

                # 增加批处理间延迟，让出CPU时间给其他协程
                if i + batch_size < need_switch_count:
                    await asyncio.sleep(BATCH_PROCESS_DELAY)

            if total_success > 0 or total_errors > 0:
                logger.info(
                    f"自动切换轮次完成: 总成功 {total_success}，总失败 {total_errors}，"
                    f"跳过缓存 {cached_skip_count}，检查总数 {total_groups}"
                )

        except Exception as e:
            logger.error(f"自动切换任务异常: {e}")
            await asyncio.sleep(30)  # 异常时延长等待时间

        await asyncio.sleep(AUTO_SWITCH_INTERVAL)


from nonebot import get_driver

driver = get_driver()
_auto_switch_task = None


@driver.on_startup
async def start_auto_switch():
    global _auto_switch_task, _recovery_task
    _auto_switch_task = asyncio.create_task(auto_switch_task())
    _recovery_task = asyncio.create_task(recovery_task())
    logger.info("智能机器人管理系统已启动 (将在延迟后开始监控)")


async def recovery_task():
    """定期检查和恢复故障机器人"""
    await asyncio.sleep(8)  # 比auto_switch_task稍晚启动
    logger.info("开始执行故障恢复任务监控")

    last_recovery_time = 0

    while True:
        try:
            current_time = time.time()

            # 智能调整恢复检查间隔
            time_since_last = current_time - last_recovery_time
            if time_since_last < RECOVERY_INTERVAL:
                await asyncio.sleep(RECOVERY_INTERVAL - time_since_last)
                continue

            last_recovery_time = current_time

            # 清理后台任务，但频率更低
            if len(_background_tasks) > 20:
                cleanup_background_tasks()

            available_bots = get_cached_bots()
            if available_bots:
                await BotFailureMonitor.check_recovery()
            else:
                logger.debug("无可用机器人，跳过恢复检查")

        except Exception as e:
            logger.error(f"恢复检查任务异常: {e}")
            await asyncio.sleep(30)  # 异常时延长等待时间

        await asyncio.sleep(RECOVERY_INTERVAL)


@driver.on_startup
async def start_recovery_task():
    pass


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
        try:
            group_member_list = await bot.get_group_member_list(group_id=int(group_id))
            member_ids = [str(member["user_id"]) for member in group_member_list]
            is_in_group = bot_id in member_ids

            if is_in_group:
                logger.debug(f"机器人 {bot_id} 确认在群 {group_id} 中")
            else:
                logger.debug(f"机器人 {bot_id} 不在群 {group_id} 的成员列表中")

            return is_in_group

        except Exception as e:
            logger.debug(f"机器人 {bot_id} 无法获取群 {group_id} 成员列表: {e}")
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

    available_bots = get_cached_bots()
    online_bot_ids = [bot_id for bot_id in bot_ids if bot_id in available_bots]

    if not online_bot_ids:
        return []

    # 限制并发数量，避免过多请求
    if len(online_bot_ids) > 5:
        logger.debug(f"群组 {group_id} 有 {len(online_bot_ids)} 个机器人，使用采样检查")
        sample_bot_id = online_bot_ids[0]
    else:
        sample_bot_id = online_bot_ids[0]

    sample_bot = available_bots[sample_bot_id]

    try:
        # 添加超时，避免长时间阻塞
        group_member_list = await asyncio.wait_for(
            sample_bot.get_group_member_list(group_id=int(group_id)),
            timeout=10.0,  # 10秒超时
        )
        member_ids = {str(member["user_id"]) for member in group_member_list}
        bots_in_group = []
        for bot_id in online_bot_ids:
            if bot_id in member_ids:
                bots_in_group.append(bot_id)
                logger.debug(f"机器人 {bot_id} 确认在群 {group_id} 中")
            else:
                logger.debug(f"机器人 {bot_id} 不在群 {group_id} 的成员列表中")

        return bots_in_group

    except TimeoutError:
        logger.warning(f"获取群 {group_id} 成员列表超时，回退到逐个检查")
        return await _fallback_individual_check(online_bot_ids, group_id)
    except Exception as e:
        logger.warning(f"批量检查机器人在群 {group_id} 时出错: {e}")
        logger.info(f"回退到逐个检查机器人是否在群 {group_id} 中")
        return await _fallback_individual_check(online_bot_ids, group_id)


async def _fallback_individual_check(bot_ids: list[str], group_id: str) -> list[str]:
    """回退到逐个检查机器人状态"""
    # 限制并发数量，每次最多检查5个
    batch_size = 5
    all_results = []

    for i in range(0, len(bot_ids), batch_size):
        batch = bot_ids[i : i + batch_size]
        check_tasks = [check_bot_in_group(bot_id, group_id) for bot_id in batch]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*check_tasks, return_exceptions=True),
                timeout=15.0,  # 15秒总超时
            )

            for bot_id, result in zip(batch, results):
                if isinstance(result, bool) and result:
                    all_results.append(bot_id)
                elif isinstance(result, Exception):
                    logger.warning(f"检查机器人 {bot_id} 时发生异常: {result}")

        except TimeoutError:
            logger.warning(f"批次检查超时，跳过 {len(batch)} 个机器人")

        # 批次间短暂延迟
        if i + batch_size < len(bot_ids):
            await asyncio.sleep(0.5)

    return all_results


async def get_bots_in_group(group_id: str) -> list[str]:
    """获取指定群组中的所有机器人"""
    if group_id in _group_bots_cache:
        return _group_bots_cache[group_id]
    available_bots = get_cached_bots()
    bot_ids = list(available_bots.keys())
    bots_in_group = await check_bots_in_group_batch(bot_ids, group_id)
    _group_bots_cache[group_id] = bots_in_group

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
            available_bots = get_cached_bots()
            if bot_id not in available_bots:
                return False, "机器人离线"
            if BotFailureMonitor.is_bot_disabled(bot_id):
                return False, "机器人被故障监控禁用"
            status_info = BotFailureMonitor.get_bot_status(bot_id)
            if status_info["status"] == "disabled":
                return False, "机器人处于禁用状态"
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
        if current_time - bot_failures[bot_id]["last_failure"] > FAILURE_WINDOW:
            bot_failures[bot_id]["count"] = 0
            failed_actions[bot_id].clear()
        bot_failures[bot_id]["count"] += 1
        bot_failures[bot_id]["last_failure"] = current_time
        bot_failures[bot_id]["errors"].append(
            {"time": current_time, "action": action_type, "error": error}
        )
        failed_actions[bot_id].add(action_type)

        logger.warning(f"机器人 {bot_id} 发生故障: {action_type} - {error}")
        logger.debug(
            f"故障详情 - 机器人: {bot_id}, 类型: {action_type}, "
            f"当前故障数: {bot_failures[bot_id]['count']}, "
            f"阈值: {FAILURE_THRESHOLD}"
        )
        if bot_failures[bot_id]["count"] >= FAILURE_THRESHOLD:
            was_already_disabled = current_time < bot_failures[bot_id].get(
                "disabled_until", 0
            )

            bot_failures[bot_id]["disabled_until"] = current_time + DISABLE_DURATION
            logger.error(
                f"机器人 {bot_id} 故障次数过多，临时禁用 {DISABLE_DURATION / 60:.1f} 分钟"
            )
            if not was_already_disabled:
                logger.info(f"机器人 {bot_id} 首次被禁用，触发自动故障转移")
                task = asyncio.create_task(BotFailureMonitor.auto_failover(bot_id))
                _background_tasks.append(task)
            else:
                logger.debug(f"机器人 {bot_id} 已被禁用，延长禁用时间但不重复故障转移")

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
        # 并发控制
        if not await ConcurrencyLimiter.acquire("failovers"):
            logger.debug(f"群组 {channel.guildId} 故障转移被并发限制跳过")
            return

        try:
            group_id = channel.guildId

            # 主动让出控制权
            await yield_control()

            bots_in_group = await get_bots_in_group(group_id)
            if len(bots_in_group) <= 1:
                logger.info(
                    f"群组 {group_id} 只有 {len(bots_in_group)} 个机器人，跳过故障转移"
                )
                return

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

            # 再次让出控制权
            await yield_control()

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
        finally:
            ConcurrencyLimiter.release("failovers")

    @staticmethod
    async def auto_failover(failed_bot_id: str):
        """自动故障转移"""
        try:
            start_time = time.time()

            # 使用过滤查询，减少数据库负载
            channels = await Channel.filter(assignee=failed_bot_id)

            if not channels:
                logger.debug(f"未找到使用机器人 {failed_bot_id} 的群组")
                return

            total_channels = len(channels)
            logger.info(
                f"开始故障转移：机器人 {failed_bot_id} 涉及 {total_channels} 个群组"
            )

            valid_channels = []
            cached_non_switchable = 0

            for channel in channels:
                is_cached, cache_reason = is_group_non_switchable_cached(
                    channel.guildId
                )
                if is_cached:
                    cached_non_switchable += 1
                    logger.debug(
                        f"群组 {channel.guildId} 已缓存为不可切换({cache_reason})，跳过故障转移"
                    )
                else:
                    valid_channels.append(channel)

            if cached_non_switchable > 0:
                logger.info(f"跳过 {cached_non_switchable} 个已缓存的不可切换群组")

            if not valid_channels:
                logger.info("所有群组均为不可切换状态，故障转移完成")
                return

            # 减少并发数量，降低对其他协程的影响
            max_concurrent = min(6, len(valid_channels))  # 最多6个并发

            success_count = 0
            error_count = 0
            no_alternative_count = 0
            error_details = []

            # 分批处理，避免一次性创建过多任务
            for i in range(0, len(valid_channels), max_concurrent):
                batch = valid_channels[i : i + max_concurrent]

                failover_tasks = [
                    BotFailureMonitor.process_failover_for_channel(
                        channel, failed_bot_id
                    )
                    for channel in batch
                ]

                results = await asyncio.gather(*failover_tasks, return_exceptions=True)

                for j, result in enumerate(results):
                    channel = batch[j]
                    if isinstance(result, Exception):
                        error_count += 1
                        error_msg = str(result)
                        error_details.append(f"群组 {channel.guildId}: {error_msg}")
                        if (
                            "没有找到合适的替代机器人" in error_msg
                            or "无可用机器人" in error_msg
                        ):
                            no_alternative_count += 1
                            cache_non_switchable_group(
                                channel.guildId,
                                "无替代机器人可用",
                                180,  # 短期缓存，3分钟后重试
                            )
                    else:
                        success_count += 1

                # 批次间延迟，让出CPU时间
                if i + max_concurrent < len(valid_channels):
                    await asyncio.sleep(1.0)

            elapsed_time = time.time() - start_time
            summary_parts = [
                f"故障转移完成 (耗时 {elapsed_time:.2f}s)",
                f"总群组: {total_channels}",
                f"成功: {success_count}",
            ]

            if cached_non_switchable > 0:
                summary_parts.append(f"缓存跳过: {cached_non_switchable}")

            if error_count > 0:
                summary_parts.append(f"失败: {error_count}")
                if no_alternative_count > 0:
                    summary_parts.append(f"无替代机器人: {no_alternative_count}")

            summary_msg = ", ".join(summary_parts)

            if error_count > 0:
                logger.warning(summary_msg)
                for error_detail in error_details[:3]:
                    logger.debug(f"故障转移错误详情: {error_detail}")
                if len(error_details) > 3:
                    logger.debug(f"还有 {len(error_details) - 3} 个错误未显示...")
            else:
                logger.info(summary_msg)

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
        # 并发控制
        if not await ConcurrencyLimiter.acquire("recoveries"):
            return bot_id, False, "并发限制"

        try:
            current_time = time.time()
            failure_info = bot_failures[bot_id]

            if current_time >= failure_info.get("disabled_until", 0):
                if failure_info.get("disabled_until", 0) > 0:  # 之前被禁用过
                    bot = available_bots[bot_id]

                    # 主动让出控制权
                    await yield_control()

                    await asyncio.wait_for(bot.get_login_info(), timeout=8.0)
                    return bot_id, True, ""

            return bot_id, False, "未到恢复时间"
        except TimeoutError:
            return bot_id, False, "恢复检查超时"
        except Exception as e:
            return bot_id, False, str(e)
        finally:
            ConcurrencyLimiter.release("recoveries")

    @staticmethod
    async def check_recovery():
        """检查故障机器人是否已恢复"""
        current_time = time.time()
        available_bots = get_cached_bots()
        bots_to_check = []

        for bot_id in list(bot_failures.keys()):
            if bot_id in available_bots:
                failure_info = bot_failures[bot_id]
                if current_time >= failure_info.get("disabled_until", 0):
                    if failure_info.get("disabled_until", 0) > 0:  # 之前被禁用过
                        bots_to_check.append(bot_id)

        if not bots_to_check:
            return

        logger.info(f"检查 {len(bots_to_check)} 个机器人的恢复状态")

        # 限制并发恢复检查数量
        max_concurrent = min(4, len(bots_to_check))
        recovered_count = 0
        failed_count = 0

        # 分批处理恢复检查
        for i in range(0, len(bots_to_check), max_concurrent):
            batch = bots_to_check[i : i + max_concurrent]

            recovery_tasks = [
                BotFailureMonitor.check_bot_recovery(bot_id, available_bots)
                for bot_id in batch
            ]

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*recovery_tasks, return_exceptions=True),
                    timeout=20.0,  # 20秒总超时
                )

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"恢复检查异常: {result}")
                        continue

                    if not isinstance(result, tuple) or len(result) != 3:
                        logger.error(f"恢复检查返回格式错误: {result}")
                        continue

                    bot_id, is_recovered, error_msg = result

                    if is_recovered:
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
                        if bot_id in bot_failures:
                            bot_failures[bot_id]["disabled_until"] = (
                                current_time + DISABLE_DURATION
                            )
                            logger.warning(
                                f"机器人 {bot_id} 恢复检查失败，延长禁用时间: {error_msg}"
                            )
                            failed_count += 1

            except TimeoutError:
                logger.warning(f"恢复检查批次超时，跳过 {len(batch)} 个机器人")
                failed_count += len(batch)

            # 批次间延迟
            if i + max_concurrent < len(bots_to_check):
                await asyncio.sleep(0.8)

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


@event_preprocessor
async def track_bot_activity(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)


bot_health_cmd: type[Matcher] = on_command(
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
        failed_actions_list = status_info.get("failed_actions", [])
        if failed_actions_list:
            failed_actions_str = ", ".join(failed_actions_list)
            msg_parts.append(f"   └ 失败操作: {failed_actions_str}")

    if len(msg_parts) == 1:
        msg_parts.append("暂无机器人在线")

    await bot_health_cmd.finish("\n".join(msg_parts))


clear_cache_cmd = on_command(
    "clear_bot_cache", aliases={"清理机器人缓存"}, permission=SUPERUSER, priority=5
)


@clear_cache_cmd.handle()
async def handle_clear_cache(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)
    clear_bots_cache()
    short_term_count = len(_short_term_non_switchable_cache)
    default_count = len(_non_switchable_groups_cache)
    long_term_count = len(_long_term_non_switchable_cache)

    _short_term_non_switchable_cache.clear()
    _non_switchable_groups_cache.clear()
    _long_term_non_switchable_cache.clear()

    total_non_switchable = short_term_count + default_count + long_term_count

    await clear_cache_cmd.finish(
        f"✅ 已清理所有缓存\n"
        f"- 机器人状态缓存\n"
        f"- 群组机器人列表缓存: {len(_group_bots_cache)} 个\n"
        f"- 无法切换群组缓存: {total_non_switchable} 个\n"
        f"  └ 短期缓存: {short_term_count} 个\n"
        f"  └ 默认缓存: {default_count} 个\n"
        f"  └ 长期缓存: {long_term_count} 个"
    )


cache_stats_cmd = on_command(
    "cache_stats", aliases={"缓存统计"}, permission=SUPERUSER, priority=5
)


@cache_stats_cmd.handle()
async def handle_cache_stats(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)
    group_bots_stats = f"{len(_group_bots_cache)}/{_group_bots_cache.maxsize}"
    short_term_stats = f"{len(_short_term_non_switchable_cache)}/{_short_term_non_switchable_cache.maxsize}"
    default_stats = (
        f"{len(_non_switchable_groups_cache)}/{_non_switchable_groups_cache.maxsize}"
    )
    long_term_stats = f"{len(_long_term_non_switchable_cache)}/{_long_term_non_switchable_cache.maxsize}"
    msg_parts = [
        "📊 缓存统计信息:",
        f"🔄 群组机器人列表缓存: {group_bots_stats} (TTL: 180s)",
        f"⏱️ 短期无法切换缓存: {short_term_stats} (TTL: 180s)",
        f"⏰ 默认无法切换缓存: {default_stats} (TTL: 900s)",
        f"🕐 长期无法切换缓存: {long_term_stats} (TTL: 3600s)",
    ]

    await cache_stats_cmd.finish("\n".join(msg_parts))


performance_stats_cmd = on_command(
    "performance_stats",
    aliases={"性能统计", "并发状态"},
    permission=SUPERUSER,
    priority=5,
)


@performance_stats_cmd.handle()
async def handle_performance_stats(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)

    # 获取并发统计
    concurrent_stats = ConcurrencyLimiter.get_stats()

    # 获取后台任务统计
    background_task_count = len(_background_tasks)

    # 获取缓存统计
    cache_stats = {
        "群组机器人": f"{len(_group_bots_cache)}/{_group_bots_cache.maxsize}",
        "短期无法切换": f"{len(_short_term_non_switchable_cache)}/{_short_term_non_switchable_cache.maxsize}",
        "默认无法切换": f"{len(_non_switchable_groups_cache)}/{_non_switchable_groups_cache.maxsize}",
        "长期无法切换": f"{len(_long_term_non_switchable_cache)}/{_long_term_non_switchable_cache.maxsize}",
    }

    msg_parts = [
        "⚡ 系统性能统计:",
        "",
        "🔄 当前并发操作:",
    ]

    for op_type, current in concurrent_stats.items():
        limit = _operation_limits.get(op_type, "未知")
        msg_parts.append(f"  {op_type}: {current}/{limit}")

    msg_parts.extend(
        [
            "",
            f"📋 后台任务数量: {background_task_count}",
            "",
            "💾 缓存使用情况:",
        ]
    )

    for cache_name, usage in cache_stats.items():
        msg_parts.append(f"  {cache_name}: {usage}")

    # 添加配置信息
    msg_parts.extend(
        [
            "",
            "⚙️ 性能配置:",
            f"  自动切换间隔: {AUTO_SWITCH_INTERVAL}s",
            f"  恢复检查间隔: {RECOVERY_INTERVAL}s",
            f"  最大并发切换: {MAX_CONCURRENT_SWITCHES}",
            f"  批处理延迟: {BATCH_PROCESS_DELAY}s",
        ]
    )

    await performance_stats_cmd.finish("\n".join(msg_parts))


def cleanup_background_tasks():
    """清理已完成的后台任务，防止未 await 的 task 堆积。"""
    global _background_tasks
    if not _background_tasks:
        return

    # 批量检查任务状态，减少频繁操作
    done_tasks = []
    active_tasks = []

    for task in _background_tasks:
        if task.done():
            done_tasks.append(task)
        else:
            active_tasks.append(task)

    _background_tasks = active_tasks

    if done_tasks:
        logger.debug(
            f"清理了 {len(done_tasks)} 个已完成的后台任务，剩余 {len(active_tasks)} 个"
        )

    # 如果活跃任务过多，发出警告
    if len(active_tasks) > 30:
        logger.warning(f"后台任务数量较多: {len(active_tasks)}，可能存在性能问题")
