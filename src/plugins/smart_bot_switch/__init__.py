import time

from nonebot import get_bots, logger, on_command
from nonebot.adapters.onebot.v11 import ActionFailed, Bot, GroupMessageEvent
from nonebot.internal.matcher.matcher import Matcher
from nonebot.message import event_preprocessor, run_postprocessor
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="机器人健康监控",
    description="简单的机器人健康状态监控系统",
    usage="""
功能：
- 监控机器人活跃状态和故障
- 记录故障信息

命令：
/bot_health - 查看机器人健康状态和故障信息
""",
    type="application",
    homepage="https://github.com/nonebot/nonebot2",
    supported_adapters={"~onebot.v11"},
)

# 简单的全局状态变量
bot_activity = {}  # 记录机器人活动时间
bot_failures: dict[str, dict] = {}  # bot_id -> {count, last_failure, failed_actions}


def update_bot_activity(bot_id: str):
    """更新机器人活动时间"""
    bot_activity[bot_id] = time.time()


def is_bot_active(bot_id: str, timeout: int = 60) -> bool:
    """检查机器人是否活跃"""
    if bot_id not in bot_activity:
        return False
    return (time.time() - bot_activity[bot_id]) < timeout


class BotFailureMonitor:
    """简单的机器人故障监控"""

    @staticmethod
    def record_failure(bot_id: str, action_type: str, error_msg: str):
        """记录机器人故障"""
        current_time = time.time()

        if bot_id not in bot_failures:
            bot_failures[bot_id] = {
                "count": 0,
                "last_failure": 0,
                "failed_actions": set(),
            }

        bot_failures[bot_id]["count"] += 1
        bot_failures[bot_id]["last_failure"] = current_time
        bot_failures[bot_id]["failed_actions"].add(action_type)

        logger.warning(f"机器人 {bot_id} 故障: {action_type} - {error_msg}")

    @staticmethod
    def get_bot_status(bot_id: str) -> dict:
        """获取机器人状态"""
        if bot_id not in bot_failures:
            return {"status": "healthy", "failures": 0, "failed_actions": []}

        failure_info = bot_failures[bot_id]
        failure_count = failure_info["count"]

        # 简单的状态判断
        if failure_count == 0:
            status = "healthy"
        elif failure_count < 3:
            status = "recovering"
        else:
            status = "unhealthy"

        return {
            "status": status,
            "failures": failure_count,
            "failed_actions": list(failure_info["failed_actions"]),
        }


# 事件处理器 - 记录故障
@run_postprocessor
async def handle_action_failed(
    exception: Exception | None,
    bot: Bot,
):
    if exception and isinstance(exception, ActionFailed):
        action_type = getattr(exception, "action_type", "unknown")
        error_msg = str(exception)
        BotFailureMonitor.record_failure(bot.self_id, action_type, error_msg)


# 事件处理器 - 追踪活动
@event_preprocessor
async def track_bot_activity(bot: Bot, event: GroupMessageEvent):
    update_bot_activity(bot.self_id)


# bot_health 命令
bot_health_cmd: type[Matcher] = on_command(
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
        elif status == "unhealthy":
            status_emoji = "🔴"
            status_text = f"不健康 (故障{failures}次)"
        else:
            status_emoji = "❓"
            status_text = "未知"

        # 检查活跃状态
        is_active = is_bot_active(bot_id)
        activity_status = "活跃" if is_active else "不活跃"

        msg_parts.append(f"{status_emoji} {bot_id}: {status_text} ({activity_status})")

        # 显示失败的操作类型
        failed_actions_list = status_info.get("failed_actions", [])
        if failed_actions_list:
            failed_actions_str = ", ".join(failed_actions_list)
            msg_parts.append(f"   └ 失败操作: {failed_actions_str}")

    if len(msg_parts) == 1:
        msg_parts.append("暂无机器人在线")

    await bot_health_cmd.finish("\n".join(msg_parts))
