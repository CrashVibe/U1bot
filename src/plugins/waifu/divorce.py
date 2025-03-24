import random
import time

from cachetools import TTLCache
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent

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

    if cp := await WaifuCP.get_or_none(group_id=group_id):
        if not get_bi_mapping_contains(cp.affect, user_id):
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
    # 删除 CP 记录
    cp_record = await WaifuCP.get_or_none(group_id=group_id)
    if cp_record:
        waifu_id = get_bi_mapping(cp_record.affect, user_id)
        if waifu_id:
            cp_record.affect.pop(str(user_id), None)
            cp_record.affect.pop(str(waifu_id), None)
            await cp_record.save()

    # 删除 Waifu 记录
    waifu_record = await PWaifu.get_or_none(group_id=group_id)
    if waifu_record:
        if str(user_id) in waifu_record.waifu_list:
            waifu_record.waifu_list.remove(user_id)
        if waifu_id and str(waifu_id) in waifu_record.waifu_list:
            waifu_record.waifu_list.remove(waifu_id)
        await waifu_record.save()

    # 删除锁记录
    lock_record = await WaifuLock.get_or_none(group_id=group_id)
    if lock_record:
        if str(user_id) in lock_record.lock:
            del lock_record.lock[str(user_id)]
        if waifu_id and str(waifu_id) in lock_record.lock:
            del lock_record.lock[str(waifu_id)]
        await lock_record.save()
