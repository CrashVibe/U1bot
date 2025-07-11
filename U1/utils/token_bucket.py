from asyncio import get_running_loop
from collections import defaultdict
from enum import IntEnum, auto

from nonebot.adapters.milky.event import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Depends


class CooldownIsolateLevel(IntEnum):
    """命令冷却的隔离级别"""

    GLOBAL = auto()
    """全局使用同一个冷却计时"""
    GROUP = auto()
    """群组内使用同一个冷却计时"""
    USER = auto()
    """按用户使用同一个冷却计时"""
    GROUP_USER = auto()
    """群组内每个用户使用同一个冷却计时"""


def Cooldown(
    cooldown: float = 5,
    *,
    prompt: str | None = None,
    isolate_level: CooldownIsolateLevel = CooldownIsolateLevel.USER,
    parallel: int = 1,
) -> None:
    """依赖注入形式的事件冷却

    用法:
        ```python
        @matcher.handle(parameterless=[Cooldown(cooldown=11.4514, ...)])
        async def handle_command(matcher: Matcher, message: Message):
            ...
        ```

    参数:
        cooldown: 冷却间隔
        prompt: 当触发冷却时发送给用户的提示消息
        isolate_level: 事件冷却的隔离级别, 参考 `CooldownIsolateLevel`
        parallel: 并行执行的命令数量
    """
    if not isinstance(isolate_level, CooldownIsolateLevel):
        raise ValueError(
            f"invalid isolate level: {isolate_level!r}, "
            "isolate level must use provided enumerate value."
        )
    running: defaultdict[str, int] = defaultdict(lambda: parallel)

    def increase(key: str, value: int = 1):
        running[key] += value
        if running[key] >= parallel:
            del running[key]
        return

    async def dependency(matcher: Matcher, event: MessageEvent):
        loop = get_running_loop()


        if isolate_level is CooldownIsolateLevel.GROUP:
            if event.data.message_scene == "group":
                key = str(event.data.peer_id)
            else:
                raise ValueError(
                    "isolate_level is set to GROUP, but event is not a group message."
                )
        elif isolate_level is CooldownIsolateLevel.USER:
            key = event.get_user_id()
        elif isolate_level is CooldownIsolateLevel.GROUP_USER:
            key = event.get_session_id()
        else:
            key = CooldownIsolateLevel.GLOBAL.name

        if not key:
            return

        if running[key] <= 0:
            await matcher.finish(prompt)
        else:
            running[key] -= 1
            loop.call_later(cooldown, lambda: increase(key))
        return

    return Depends(dependency)
