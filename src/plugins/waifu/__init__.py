import random
from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import get_driver, logger, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_apscheduler import scheduler
from typing import Any

from .card_pool import card_pool
from .cp_list import cp_list
from .divorce import bye
from .record import record
from .yinpa import yinpa

__all__ = ["bye", "card_pool", "cp_list", "record", "yinpa"]
from .config import Config, settings
from .models import (
    PWaifu,
    WaifuCP,
    WaifuLock,
)
from .utils import (
    get_bi_mapping,
    get_bi_mapping_contains,
    get_message_at,
    get_protected_users,
    user_img,
)

__plugin_meta__ = PluginMetadata(name="娶群友", description="", usage="", config=Config)

waifu_config = settings
waifu_cd_bye = waifu_config.waifu_cd_bye
waifu_save = waifu_config.waifu_save
waifu_reset = waifu_config.waifu_reset
last_sent_time_filter = waifu_config.waifu_last_sent_time_filter
HE = waifu_config.waifu_he
yinpa_HE = waifu_config.yinpa_he
yinpa_CP = waifu_config.yinpa_cp
yinpa_CP = min(yinpa_CP, 100 - yinpa_HE)
Bot_NICKNAME = list(get_driver().config.nickname)
Bot_NICKNAME = Bot_NICKNAME[0] if Bot_NICKNAME else "bot"
no_waifu = [
    "你没有娶到群友，强者注定孤独，加油！",
    "找不到对象.jpg",
    "雪花飘飘北风萧萧～天地一片苍茫。",
    "要不等着分配一个对象？",
    "恭喜伱没有娶到老婆~",
    "さんが群友で結婚するであろうヒロインは、\n『自分の左手』です！",
    "醒醒，伱没有老婆。",
    "哈哈哈哈哈哈哈哈哈",
    "智者不入爱河，建设美丽中国。",
    "智者不入爱河，我们终成富婆",
    "智者不入爱河，寡王一路硕博",
    "娶不到就是娶不+-到，娶不到就多练！",
]

happy_end = [
    "好耶~",
    "婚礼？启动！",
    "需要咱主持婚礼吗 qwq",
    "不许秀恩爱！",
    "(响起婚礼进行曲♪)",
    "比翼从此添双翅，连理于今有合枝。\n琴瑟和鸣鸳鸯栖，同心结结永相系。",
    "金玉良缘，天作之合，郎才女貌，喜结同心。",
    "繁花簇锦迎新人，车水马龙贺新婚。",
    "乾坤和乐，燕尔新婚。",
    "愿天下有情人终成眷属。",
    "花团锦绣色彩艳，嘉宾满堂话语喧。",
    "火树银花不夜天，春归画栋双栖燕。",
    "红妆带绾同心结，碧树花开并蒂莲。",
    "一生一世两情相悦，三世尘缘四世同喜",
    "玉楼光辉花并蒂，金屋春暖月初圆。",
    "笙韵谱成同生梦，烛光笑对含羞人。",
    "祝你们百年好合，白头到老。",
    "祝你们生八个。",
]

cd_bye = {}


async def safe_delete(query: Any, using_db: Any | None = None) -> Any:
    return await query.delete()


async def reset_record():
    logger.info("定时重置娶群友记录")
    yesterday = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    models_to_clean = [WaifuCP, PWaifu, WaifuLock]
    for model in models_to_clean:
        await safe_delete(model.filter(created_at=yesterday))


async def mo_reset_record():
    logger.info("手动重置娶群友记录")
    yesterday = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    models_to_clean: list[type[Any]] = [
        WaifuCP,
        PWaifu,
        WaifuLock,
    ]
    for model in models_to_clean:
        await safe_delete(model.filter(created_at=yesterday))


on_command("重置记录", permission=SUPERUSER, block=True).append_handler(mo_reset_record)

scheduler.add_job(reset_record, "cron", hour=0, minute=0, misfire_grace_time=120)

waifu = on_command("娶群友", block=True)


@waifu.handle()
async def handle_waifu(bot: Bot, event: GroupMessageEvent):
    if not await validate_user(bot, event):
        return

    group_id = event.group_id
    user_id = event.user_id

    # 获取 CP 记录
    cp_record, _ = await WaifuCP.get_or_create(group_id=group_id)

    # 检查已有 CP
    if existing_cp := get_bi_mapping(cp_record.affect, user_id):
        return await handle_existing_cp(bot, event, existing_cp)

    # 选择逻辑
    selected = await select_waifu(bot, event, cp_record)
    if not selected:
        return await waifu.finish(random.choice(no_waifu), at_sender=True)

    # 保存记录
    await update_records(group_id, user_id, selected)
    await send_result(bot, event, selected)


async def select_waifu(
    bot: Bot, event: GroupMessageEvent, cp_record: WaifuCP
) -> int | None:
    """核心选择逻辑"""
    group_id = event.group_id
    user_id = event.user_id
    protected = await get_protected_users(group_id)
    select = None
    # 尝试通过 @ 选择
    if at := get_message_at(event.message):
        select = await handle_at_selection(bot, event, at[0], protected, cp_record)
    if select is not None:
        return select
    members = await get_available_members(bot, group_id, protected)
    select = random.choice(members)
    if select == user_id or get_bi_mapping_contains(cp_record.affect, select):
        return None
    return select


async def get_available_members(bot: Bot, group_id: int, protected: list) -> list[int]:
    return [
        member["user_id"]
        for member in await bot.get_group_member_list(group_id=group_id)
        if member["user_id"] not in [*protected, bot.self_id, 2854196310]
    ]


async def validate_user(bot: Bot, event: GroupMessageEvent) -> bool:
    if event.to_me:
        await bot.send(event, "不可以啦...", at_sender=True)
        return False

    protected = await get_protected_users(event.group_id)
    if event.user_id in protected:
        return False

    return True


async def handle_existing_cp(bot: Bot, event: GroupMessageEvent, existing_cp: int):
    member = await bot.get_group_member_info(
        group_id=event.group_id, user_id=existing_cp
    )
    msg = (
        f"你已经有 CP 了，不许花心哦~{MessageSegment.image(await user_img(existing_cp))}"
        f"你的 CP：{member['card'] or member['nickname']}"
    )
    await bot.send(event, Message(msg), at_sender=True)


async def update_records(group_id: int, user_id: int, selected: int):
    record_cp, _ = await WaifuCP.get_or_create(group_id=group_id)

    record_cp.affect[str(user_id)] = selected
    await record_cp.save()

    record_waifu, _ = await PWaifu.get_or_create(group_id=group_id)
    record_waifu.waifu_list.append(selected)
    await record_waifu.save()


async def send_result(bot: Bot, event: GroupMessageEvent, selected: int):
    member = await bot.get_group_member_info(group_id=event.group_id, user_id=selected)
    msg = (
        f"你的 CP 是！\n{MessageSegment.image(await user_img(selected))}"
        f"『{member['card'] or member['nickname']}』!"
        f"\n{random.choice(happy_end)}"
    )
    await waifu.finish(Message(msg), at_sender=True)


async def handle_at_selection(
    bot: Bot,
    event: GroupMessageEvent,
    at_user_id: int,
    protected_users: list[int],
    cp_record: WaifuCP,
) -> int | None:
    """
    处理通过 @ 指定群友的逻辑
    :param event: 消息事件
    :param at_user_id: 被 @ 的用户 ID
    :param protected_users: 受保护的用户列表
    :param cp_record: CP 记录（模型实例）
    :return: 选择的用户 ID 或 None
    """
    user_id = event.user_id

    # 检查是否是自己
    if at_user_id == user_id:
        await bot.send(event, "不能娶/透自己哦~", at_sender=True)
        return None

    # 检查是否受保护
    if at_user_id in protected_users:
        return None

    # 检查是否已有 CP
    if existing_cp := get_bi_mapping(cp_record.affect, user_id):
        if at_user_id == existing_cp:
            return at_user_id
        else:
            return None

    # 随机选择逻辑
    X = random.randint(1, 100)
    if 0 < X <= HE:
        return at_user_id
    else:
        return None


async def clean_cd_cache():
    now = datetime.now(ZoneInfo("Asia/Shanghai")).timestamp()
    for group in list(cd_bye.keys()):
        cd_bye[group] = {
            uid: data for uid, data in cd_bye[group].items() if data[0] > now
        }


from nonebot_plugin_apscheduler import scheduler


def setup_scheduler():
    scheduler.add_job(
        reset_record, "cron", hour=0, minute=0, misfire_grace_time=300, coalesce=True
    )

    scheduler.add_job(clean_cd_cache, "interval", hours=1, coalesce=True)
