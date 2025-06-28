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

# 存储后台任务引用
_auto_switch_task = None
_recovery_task = None
_background_tasks = []


def update_bot_activity(bot_id: str):
    """更新机器人活动时间"""
    bot_activity[bot_id] = time.time()


def is_bot_active(bot_id: str, timeout: int = 60) -> bool:
    """检查机器人是否活跃"""
    if bot_id not in bot_activity:
        return False
    return (time.time() - bot_activity[bot_id]) < timeout


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

    # 优先级排序：活跃的健康机器人 > 活跃的机器人 > 任意在线机器人
    candidates = []

    for bot_id in group_bots:
        is_active = is_bot_active(bot_id)
        is_healthy = not BotFailureMonitor.is_bot_disabled(bot_id)

        priority = 0
        if is_active and is_healthy:
            priority = 3  # 最高优先级
        elif is_active:
            priority = 2
        elif is_healthy:
            priority = 1

        candidates.append((bot_id, priority))

    # 按优先级排序，优先级相同的随机选择
    candidates.sort(key=lambda x: x[1], reverse=True)

    if candidates:
        best_bot = candidates[0][0]
        if best_bot != channel.assignee:
            old_assignee = channel.assignee
            channel.assignee = best_bot
            await channel.save()
            logger.info(
                f"智能切换群组 {channel.guildId} 的机器人从 {old_assignee} 到 {best_bot}"
            )
        return best_bot

    return current_bot_id


# 定期检查和自动切换任务
async def auto_switch_task():
    """定期检查是否需要自动切换机器人"""
    # 启动时等待机器人连接完成
    await asyncio.sleep(10)  # 等待10秒让bot连接
    logger.info("开始执行自动切换任务监控")

    while True:
        try:
            # 获取所有频道
            channels = await Channel.all()
            available_bots = get_bots()

            # 如果没有任何机器人在线，跳过本轮检查
            if not available_bots:
                await asyncio.sleep(30)
                continue

            for channel in channels:
                if not channel.assignee:
                    continue

                # 检查当前assignee是否还有效
                needs_switch = False

                if channel.assignee not in available_bots:
                    needs_switch = True
                    # 只在有其他可用机器人时才输出警告
                    if len(available_bots) > 0:
                        logger.warning(
                            f"群组 {channel.guildId} 的assignee {channel.assignee} 不在线"
                        )
                elif not is_bot_active(channel.assignee, timeout=300):  # 5分钟无活动
                    needs_switch = True
                    logger.warning(
                        f"群组 {channel.guildId} 的assignee {channel.assignee} 长时间无活动"
                    )
                else:
                    # 检查故障状态
                    if BotFailureMonitor.is_bot_disabled(channel.assignee):
                        needs_switch = True
                        logger.warning(
                            f"群组 {channel.guildId} 的assignee {channel.assignee} 已被故障监控禁用"
                        )

                if needs_switch:
                    await smart_assign_bot(channel, channel.assignee)

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
            available_bots = get_bots()
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

    available_bots = get_bots()
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
    available_bots = get_bots()

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
        available_bots = get_bots()
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


async def get_bots_in_group(group_id: str) -> list[str]:
    """获取指定群组中的所有机器人"""
    available_bots = get_bots()
    bots_in_group = []

    for bot_id in available_bots.keys():
        if await check_bot_in_group(bot_id, group_id):
            bots_in_group.append(bot_id)

    return bots_in_group


class BotFailureMonitor:
    """机器人故障监控和自动恢复"""

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
    async def auto_failover(failed_bot_id: str):
        """自动故障转移"""
        try:
            # 查找所有使用该机器人的群组
            channels = await Channel.filter(assignee=failed_bot_id)

            if not channels:
                return

            available_bots = get_bots()

            # 寻找可用的替代机器人
            backup_bot = None
            for bot_id in available_bots.keys():
                if bot_id != failed_bot_id and not BotFailureMonitor.is_bot_disabled(
                    bot_id
                ):
                    backup_bot = bot_id
                    break

            if not backup_bot:
                logger.error(f"无法为故障机器人 {failed_bot_id} 找到可用的备用机器人")
                return

            # 检查每个群组，只为有多个机器人的群组进行切换
            for channel in channels:
                group_id = channel.guildId

                # 检查该群组中有多少个机器人
                bots_in_group = await get_bots_in_group(group_id)

                # 如果群里只有故障机器人一个，则不进行切换
                if len(bots_in_group) <= 1:
                    logger.info(
                        f"群组 {group_id} 只有 {len(bots_in_group)} 个机器人，跳过故障转移"
                    )
                    continue

                # 检查备用机器人是否在这个群里
                if backup_bot not in bots_in_group:
                    logger.warning(
                        f"备用机器人 {backup_bot} 不在群组 {group_id} 中，跳过切换"
                    )
                    continue

                old_assignee = channel.assignee
                channel.assignee = backup_bot
                await channel.save()
                logger.info(
                    f"故障转移: 群组 {channel.guildId} 从 {old_assignee} 切换到 {backup_bot} (群内有{len(bots_in_group)}个机器人)"
                )

        except Exception as e:
            logger.error(f"自动故障转移失败: {e}")

    @staticmethod
    async def check_recovery():
        """检查故障机器人是否已恢复"""
        current_time = time.time()
        available_bots = get_bots()

        for bot_id in list(bot_failures.keys()):
            if bot_id not in available_bots:
                continue

            failure_info = bot_failures[bot_id]

            # 检查是否到达恢复时间
            if current_time >= failure_info.get("disabled_until", 0):
                if failure_info.get("disabled_until", 0) > 0:  # 之前被禁用过
                    logger.info(f"机器人 {bot_id} 禁用期已过，尝试恢复检查")

                    # 尝试简单的健康检查
                    bot = available_bots[bot_id]
                    try:
                        await bot.get_login_info()
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

                    except Exception as e:
                        # 延长禁用时间
                        failure_info["disabled_until"] = current_time + DISABLE_DURATION
                        logger.warning(
                            f"机器人 {bot_id} 恢复检查失败，延长禁用时间: {e}"
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

    available_bots = get_bots()
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
