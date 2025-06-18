import random
import time

from cachetools import TTLCache
from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import GroupMessageEvent

require("nonebot_plugin_orm")
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import PWaifu, WaifuCP, WaifuLock
from .utils import get_bi_mapping, get_bi_mapping_contains

# 初始化全局缓存
last_reset_cache = TTLCache(maxsize=1000, ttl=86400)  # 24小时过期
cd_cache = TTLCache(maxsize=1000, ttl=3600)  # 1小时过期

bye = on_command("离婚", aliases={"分手"}, block=True)


@bye.handle()
async def handle_divorce(event: GroupMessageEvent):
    user_id = event.user_id
    group_id = event.group_id

    async with get_session() as session:
        cp_stmt = select(WaifuCP).where(WaifuCP.group_id == group_id)
        cp_result = await session.execute(cp_stmt)
        cp = cp_result.scalar_one_or_none()

        if cp and not get_bi_mapping_contains(cp.affect, user_id):
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
        waifu_id = None

        # 删除 CP 记录
        cp_stmt = select(WaifuCP).where(WaifuCP.group_id == group_id)
        cp_result = await session.execute(cp_stmt)
        cp_record = cp_result.scalar_one_or_none()

        if cp_record:
            waifu_id = get_bi_mapping(cp_record.affect, user_id)
            if waifu_id:
                cp_record.affect.pop(str(user_id), None)
                cp_record.affect.pop(str(waifu_id), None)
                session.add(cp_record)

        # 删除 Waifu 记录
        waifu_stmt = select(PWaifu).where(PWaifu.group_id == group_id)
        waifu_result = await session.execute(waifu_stmt)
        waifu_record = waifu_result.scalar_one_or_none()

        if waifu_record:
            if user_id in waifu_record.waifu_list:
                waifu_record.waifu_list.remove(user_id)
            if waifu_id and waifu_id in waifu_record.waifu_list:
                waifu_record.waifu_list.remove(waifu_id)
            session.add(waifu_record)

        # 删除锁记录
        lock_stmt = select(WaifuLock).where(WaifuLock.group_id == group_id)
        lock_result = await session.execute(lock_stmt)
        lock_record = lock_result.scalar_one_or_none()

        if lock_record:
            if str(user_id) in lock_record.lock:
                del lock_record.lock[str(user_id)]
            if waifu_id and str(waifu_id) in lock_record.lock:
                del lock_record.lock[str(waifu_id)]
            session.add(lock_record)

        await session.commit()
