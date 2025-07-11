import random
import time

from cachetools import TTLCache
from nonebot import on_command, require
from nonebot.adapters.milky import Bot, Message, MessageSegment
from nonebot.adapters.milky.event import GroupMessageEvent

require("nonebot_plugin_orm")
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .config import settings
from .models import YinpaActive, YinpaPassive
from .utils import get_message_at, get_protected_users, user_img

cd_cache = TTLCache(maxsize=1000, ttl=3600)  # 1小时过期

yinpa_config = settings
YINPA_HE = yinpa_config.yinpa_he
YINPA_BE = yinpa_config.yinpa_be

yinpa = on_command("透群友", block=True, priority=10)


@yinpa.handle()
async def handle_yinpa(bot: Bot, event: GroupMessageEvent):
    # 检查目标用户
    targets = get_message_at(event.message)
    user_id = event.data.sender_id
    group_id = event.data.peer_id

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
    async with get_session() as session:
        # 更新主动记录
        active_stmt = select(YinpaActive).where(YinpaActive.user_id == user_id)
        active_result = await session.execute(active_stmt)
        active_record = active_result.scalar_one_or_none()

        if active_record is None:
            active_record = YinpaActive(user_id=user_id, active_count=1)
            session.add(active_record)
        else:
            active_record.active_count += 1

        # 更新被动记录
        passive_stmt = select(YinpaPassive).where(YinpaPassive.user_id == target)
        passive_result = await session.execute(passive_stmt)
        passive_record = passive_result.scalar_one_or_none()

        if passive_record is None:
            passive_record = YinpaPassive(user_id=target, passive_count=1)
            session.add(passive_record)
        else:
            passive_record.passive_count += 1

        await session.commit()

    # 生成结果消息
    msg = await generate_yinpa_result(bot, event, success, target)
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
        member.user_id
        for member in members
        if member.user_id not in protected
        and member.user_id not in exclude
        and member.user_id != int(bot.self_id)
    ]


def check_yinpa_cd(event: GroupMessageEvent) -> bool:
    """检查涩涩CD"""
    key = f"yinpa_{event.data.peer_id}_{event.data.sender_id}"
    last_time = cd_cache.get(key, 0)
    if time.time() - last_time < 300:  # 5分钟CD
        return False
    cd_cache[key] = time.time()
    return True


async def process_yinpa() -> bool:
    """涩涩成功率计算"""
    rand = random.randint(1, 100)
    return rand <= YINPA_HE


async def generate_yinpa_result(
    bot: Bot, event: GroupMessageEvent, success: bool, target: int
) -> Message:
    """生成涩涩结果消息"""
    # 获取目标用户信息
    member = await bot.get_group_member_info(
        group_id=event.data.peer_id, user_id=target
    )
    target_name = member.card or member.nickname

    if success:
        success_messages = [
            "成功了！",
            "大成功！",
            "完美执行！",
            "太棒了！",
            "成功完成了不可描述之事！",
            "任务达成！",
        ]
        msg = (
            f"{random.choice(success_messages)}\n"
            f"{MessageSegment.image(await user_img(target))}"
            f"目标：『{target_name}』\n"
            f"结果：成功 {random.choice(['🥵', '😋', '🤤', '💕', '✨'])}"
        )
    else:
        fail_messages = [
            "失败了...",
            "被反杀了！",
            "任务失败！",
            "翻车了！",
            "被发现了！",
            "计划败露！",
        ]
        msg = (
            f"{random.choice(fail_messages)}\n"
            f"{MessageSegment.image(await user_img(target))}"
            f"目标：『{target_name}』\n"
            f"结果：失败 {random.choice(['😭', '😨', '💔', '😵', '🤕'])}"
        )

    return Message(msg)
