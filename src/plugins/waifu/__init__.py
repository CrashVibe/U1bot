import random
from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import get_driver, logger, on_command, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_apscheduler import scheduler

require("nonebot_plugin_orm")
from sqlalchemy import delete, select

from .card_pool import card_pool
from .cp_list import cp_list
from .divorce import bye
from .record import record
from .yinpa import yinpa

__all__ = ["bye", "card_pool", "cp_list", "record", "yinpa"]
from .config import Config, settings
from .models import (
    WaifuLock,
    WaifuRelationship,
)
from .utils import (
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


async def reset_record():
    logger.info("定时重置娶群友记录")
    yesterday = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    from nonebot_plugin_orm import get_session

    async with get_session() as session:
        # 删除所有关系记录
        delete_relationships = delete(WaifuRelationship).where(
            WaifuRelationship.created_at < yesterday
        )
        await session.execute(delete_relationships)

        # 删除过期的锁定记录
        delete_locks = delete(WaifuLock).where(
            (WaifuLock.expires_at.is_not(None)) & (WaifuLock.expires_at < yesterday)
        )
        await session.execute(delete_locks)

        await session.commit()


async def mo_reset_record():
    logger.info("手动重置娶群友记录")
    yesterday = datetime.now(ZoneInfo("Asia/Shanghai")).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    from nonebot_plugin_orm import get_session

    async with get_session() as session:
        # 删除所有关系记录
        delete_relationships = delete(WaifuRelationship).where(
            WaifuRelationship.created_at < yesterday
        )
        await session.execute(delete_relationships)

        # 删除过期的锁定记录
        delete_locks = delete(WaifuLock).where(
            (WaifuLock.expires_at.is_not(None)) & (WaifuLock.expires_at < yesterday)
        )
        await session.execute(delete_locks)

        await session.commit()


async def get_user_relationship(session, group_id: int, user_id: int):
    """获取用户的CP关系（主动方或被动方）"""
    stmt = (
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
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_relationship(session, group_id: int, user_id: int, partner_id: int):
    """创建CP关系"""
    relationship = WaifuRelationship(
        group_id=group_id, user_id=user_id, partner_id=partner_id
    )
    session.add(relationship)
    await session.commit()


async def get_taken_users(session, group_id: int) -> list[int]:
    """获取已被娶的用户列表"""
    stmt = select(WaifuRelationship.partner_id).where(
        WaifuRelationship.group_id == group_id
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.fetchall()]


scheduler.add_job(reset_record, "cron", hour=0, minute=0, misfire_grace_time=120)

waifu = on_command("娶群友", block=True)


@waifu.handle()
async def handle_waifu(bot: Bot, event: GroupMessageEvent):
    if not await validate_user(bot, event):
        return

    group_id = event.group_id
    user_id = event.user_id

    from nonebot_plugin_orm import get_session

    async with get_session() as session:
        # 检查是否已有CP
        existing_relationship = await get_user_relationship(session, group_id, user_id)
        if existing_relationship:
            # 确定伴侣ID（如果用户是主动方，取partner_id；如果是被动方，取user_id）
            if existing_relationship.user_id == user_id:
                partner_id = existing_relationship.partner_id
            else:
                partner_id = existing_relationship.user_id
            return await handle_existing_cp(bot, event, partner_id)

        # 选择逻辑
        selected = await select_waifu(bot, event, session, group_id, user_id)
        if not selected:
            return await waifu.finish(random.choice(no_waifu), at_sender=True)

        # 保存记录
        await create_relationship(session, group_id, user_id, selected)
        await send_result(bot, event, selected)


async def select_waifu(
    bot: Bot, event: GroupMessageEvent, session, group_id: int, user_id: int
) -> int | None:
    """核心选择逻辑"""
    protected = await get_protected_users(group_id)

    # 获取已被娶的人列表
    taken_users = await get_taken_users(session, group_id)

    select = None
    # 尝试通过 @ 选择
    if at := get_message_at(event.message):
        select = await handle_at_selection(bot, event, at[0], protected, taken_users)
    if select is not None:
        return select

    # 获取可用成员，排除已被娶的人和已有CP的人
    members = await get_available_members(bot, group_id, protected)
    available_members = [
        member for member in members if member != user_id and member not in taken_users
    ]

    if not available_members:
        return None

    select = random.choice(available_members)
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
    taken_users: list[int],
) -> int | None:
    """
    处理通过 @ 指定群友的逻辑
    :param event: 消息事件
    :param at_user_id: 被 @ 的用户 ID
    :param protected_users: 受保护的用户列表
    :param taken_users: 已被娶的群友列表
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

    # 检查是否已被娶
    if at_user_id in taken_users:
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

on_command("重置记录", permission=SUPERUSER, block=True).append_handler(mo_reset_record)


def setup_scheduler():
    scheduler.add_job(
        reset_record, "cron", hour=0, minute=0, misfire_grace_time=300, coalesce=True
    )

    scheduler.add_job(clean_cd_cache, "interval", hours=1, coalesce=True)
