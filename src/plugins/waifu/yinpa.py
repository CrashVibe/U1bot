import random
import time

from cachetools import TTLCache
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from tortoise.expressions import F

from .config import settings
from .models import YinpaActive, YinpaPassive
from .utils import get_message_at, get_protected_users

cd_cache = TTLCache(maxsize=1000, ttl=3600)  # 1小时过期

yinpa_config = settings
YINPA_HE = yinpa_config.yinpa_he
YINPA_BE = yinpa_config.yinpa_be

yinpa = on_command("透群友", block=True, priority=10)


@yinpa.handle()
async def handle_yinpa(bot: Bot, event: GroupMessageEvent):
    # 检查目标用户
    targets = get_message_at(event.message)
    user_id = event.user_id
    group_id = event.group_id

    if targets:
        target = targets[0]
        if event.to_me:
            await yinpa.finish("不可以啦...", at_sender=True)
    else:
        # 如果没有 @，随机选择一个目标
        protected = await get_protected_users(group_id)
        available_members = await get_available_members(
            bot, group_id, protected, exclude=[user_id]
        )
        if not available_members:
            await yinpa.finish("没有可透的群友了~", at_sender=True)
        target = random.choice(available_members)

    # 检查是否是自己
    if target == user_id:
        await yinpa.finish("不能透自己哦~", at_sender=True)

    # 执行涩涩逻辑
    success = await process_yinpa()

    # 保存记录
    await YinpaActive.filter(user_id=user_id).update(active_count=F("active_count") + 1)
    await YinpaPassive.filter(user_id=target).update(
        passive_count=F("passive_count") + 1
    )

    # 生成结果消息
    msg = generate_yinpa_result(success, target)
    await yinpa.finish(msg, at_sender=True)


async def get_available_members(
    bot: Bot, group_id: int, protected: list[int], exclude: list[int] | None = None
) -> list[int]:
    """
    获取可用的群成员列表
    :param bot: Bot 实例
    :param group_id: 群组 ID
    :param protected: 受保护的用户列表
    :param exclude: 需要排除的用户列表
    :return: 可用的用户 ID 列表
    """
    exclude = exclude or []
    members = await bot.get_group_member_list(group_id=group_id)
    return [
        member["user_id"]
        for member in members
        if member["user_id"] not in protected
        and member["user_id"] not in exclude
        and member["user_id"] != int(bot.self_id)  # 排除机器人
    ]


def check_yinpa_cd(event: GroupMessageEvent) -> bool:
    """检查涩涩CD"""
    key = f"yinpa_{event.group_id}_{event.user_id}"
    last_time = cd_cache.get(key, 0)
    if time.time() - last_time < 300:  # 5分钟CD
        return False
    cd_cache[key] = time.time()
    return True


async def process_yinpa() -> bool:
    """涩涩成功率计算"""
    rand = random.randint(1, 100)
    return rand <= YINPA_HE


def generate_yinpa_result(success: bool, passive: int) -> str:
    """生成涩涩结果消息"""
    if success:
        return f"成功对{passive}进行了不可描述之事！{random.choice(['🥵', '😋', '🤤'])}"
    else:
        return f"被{passive}反杀了！{random.choice(['😭', '😨', '💔'])}"
