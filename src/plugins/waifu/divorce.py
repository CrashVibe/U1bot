import random
import time

from cachetools import TTLCache
from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import GroupMessageEvent

require("nonebot_plugin_orm")
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select

from .models import WaifuLock, WaifuRelationship

# 初始化全局缓存
last_reset_cache = TTLCache(maxsize=1000, ttl=86400)  # 24小时过期
cd_cache = TTLCache(maxsize=1000, ttl=3600)  # 1小时过期

bye = on_command("离婚", aliases={"分手"}, block=True)


@bye.handle()
async def handle_divorce(event: GroupMessageEvent):
    user_id = event.user_id
    group_id = event.group_id

    async with get_session() as session:
        # 检查是否有CP关系（主动方或被动方）
        relationship_stmt = (
            select(WaifuRelationship)
            .where(
                WaifuRelationship.group_id == group_id,
                (
                    (WaifuRelationship.user_id == user_id)
                    | (WaifuRelationship.partner_id == user_id)
                ),
            )
            .limit(1)
        )
        relationship_result = await session.execute(relationship_stmt)
        relationship = relationship_result.scalar_one_or_none()

        if not relationship:
            await bye.finish("你还没结婚呢...", at_sender=True)

        # 正常CD逻辑
        if not check_divorce_cd(user_id):
            await bye.finish("离婚冷静期还没过呢...", at_sender=True)

    # 执行离婚
    await process_divorce(group_id, user_id)
    await bye.finish(random.choice(["嗯。", "...", "好。", "哦。", "行。"]))


def check_divorce_cd(user_id: int) -> bool:
    """
    检查离婚 CD
    :param user_id: 用户 ID
    :return: 是否允许离婚
    """
    last_time = cd_cache.get(user_id, 0)
    if time.time() - last_time < 3600:  # 1小时 CD
        return False
    cd_cache[user_id] = time.time()
    return True


async def process_divorce(group_id: int, user_id: int):
    """
    处理离婚逻辑
    :param group_id: 群组 ID
    :param user_id: 用户 ID
    """
    async with get_session() as session:
        # 查找并删除CP关系记录（主动方或被动方）
        relationship_stmt = (
            select(WaifuRelationship)
            .where(
                WaifuRelationship.group_id == group_id,
                (
                    (WaifuRelationship.user_id == user_id)
                    | (WaifuRelationship.partner_id == user_id)
                ),
            )
            .limit(1)
        )
        relationship_result = await session.execute(relationship_stmt)
        relationship = relationship_result.scalar_one_or_none()

        if relationship:
            # 确定双方的ID
            if relationship.user_id == user_id:
                partner_id = relationship.partner_id
            else:
                partner_id = relationship.user_id

            # 删除双向关系记录
            delete_stmt = delete(WaifuRelationship).where(
                WaifuRelationship.group_id == group_id,
                (
                    (WaifuRelationship.user_id == user_id)
                    & (WaifuRelationship.partner_id == partner_id)
                )
                | (
                    (WaifuRelationship.user_id == partner_id)
                    & (WaifuRelationship.partner_id == user_id)
                ),
            )
            await session.execute(delete_stmt)

            # 删除相关的锁定记录
            lock_delete_stmt = delete(WaifuLock).where(
                WaifuLock.group_id == group_id,
                (WaifuLock.user_id.in_([user_id, partner_id])),
            )
            await session.execute(lock_delete_stmt)

        await session.commit()
