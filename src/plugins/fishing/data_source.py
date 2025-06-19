import random
import time
from os import path
from pathlib import Path

import aiofiles
import ujson as json
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot_plugin_orm import get_session
from sqlalchemy import select, update

from ..coin.api import add_coin, get_coin, get_count_coin
from ..today_yunshi.models import MemberData
from .config import config
from .models import FishingRecord, FishingSwitch

luckpath = Path(path.join("./src/plugins/today_yunshi", "Fortune.json"))

fishing_coin_name = config.fishing_coin_name
fish_rotten = config.fish_rotten
fish_moldy = config.fish_moldy
fish_common = config.fish_common
fish_golden = config.fish_golden
fish_void = config.fish_void
fish_fire = config.fish_hidden_fire


async def update_sql():
    delete_fish = [
        "贴图错误鱼发霉的鲤鱼",
        "多宝鱼龙利鱼墨鱼",
        "腐烂的孙笑川鱼",
        "虚空乌贼虚空鳗鱼",
        "黄花鱼墨鱼",
    ]

    async with get_session() as session:
        stmt = select(FishingRecord)
        result = await session.execute(stmt)
        fishes_records = result.scalars().all()

        update_data = []

        for fishes_record in fishes_records:
            load_fishes = json.loads(fishes_record.fishes)
            fish_removed = False

            for fish_name in delete_fish:
                if fish_name in load_fishes:
                    del load_fishes[fish_name]
                    fish_removed = True

            # 只保留鱼的处理逻辑，移除 coin/count_coin 相关逻辑
            if fish_removed:
                dump_fishes = json.dumps(load_fishes)
                update_data.append(
                    {
                        "user_id": fishes_record.user_id,
                        "fishes": dump_fishes,
                    }
                )

        if update_data:
            for data in update_data:
                stmt = (
                    update(FishingRecord)
                    .where(FishingRecord.user_id == data["user_id"])
                    .values(fishes=data["fishes"])
                )
                await session.execute(stmt)
            await session.commit()


# 定义鱼的不同质量及其属性
fish = {
    "普通": {"weight": 100, "price_mpr": 0.1, "long": (1, 30), "fish": fish_common},
    "腐烂": {"weight": 20, "price_mpr": 0.05, "long": (15, 45), "fish": fish_rotten},
    "发霉": {"weight": 15, "price_mpr": 0.08, "long": (20, 150), "fish": fish_moldy},
    "金": {"weight": 5, "price_mpr": 0.15, "long": (125, 800), "fish": fish_golden},
    "虚空": {"weight": 3, "price_mpr": 0.2, "long": (800, 4000), "fish": fish_void},
    "隐火": {"weight": 1, "price_mpr": 0.2, "long": (1000, 4000), "fish": fish_fire},
}


def calculate_weight_increase(luck_star_num: int) -> float:
    """
    计算根据星级增加的权重（指数函数）。

    - 参数
      - luck_star_num: 用户的运势星级（0~7）
    - 返回
      - 增加的权重值
    """
    base_increase: float = 1.9
    return base_increase * (1.1**luck_star_num - 1)


MAX_WEIGHT_INCREASE = 30  # 设置权重增加上限


async def get_weight(
    user_id: str, fish_quality: list[str]
) -> tuple[list[int], bool, int | None]:
    """
    根据用户运势调整鱼的权重，并返回相应的权重值。    - 参数
      - user_id: 用户的唯一标识符
      - fish_quality: 包含鱼种质量的列表
    - 返回
      - 一个包含鱼权重的列表
      - 一个布尔值，指示是否进行了调整
      - 运势星级数（如果有的话），否则为 None
    """
    luck_star_num = None
    try:
        async with get_session() as session:
            stmt = select(MemberData).where(MemberData.user_id == user_id)
            result = await session.execute(stmt)
            luck = result.scalar_one_or_none()

            if luck is not None and luck.time.strftime("%Y-%m-%d") == time.strftime(
                "%Y-%m-%d"
            ):
                async with aiofiles.open(luckpath, encoding="utf-8") as f:
                    luckdata = json.loads(await f.read())
                    luck_star_num = (
                        luckdata.get(str(luck.luckid), {}).get("星级", "").count("★")
                    )
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing luck data: {e}")

    adjustment_made = False
    for key in fish_quality:
        if key in ["隐火", "虚空", "金"] and luck_star_num is not None:
            weight_increase = calculate_weight_increase(luck_star_num)
            new_weight = min(fish[key]["weight"] + weight_increase, MAX_WEIGHT_INCREASE)
            if new_weight != fish[key]["weight"]:
                fish[key]["weight"] = new_weight
                adjustment_made = True
    return [fish[key]["weight"] for key in fish_quality], adjustment_made, luck_star_num


async def choice(user_id: str) -> tuple[str, int, bool, int | None]:
    """
    根据用户的运势选择鱼的品质并生成相应的钓鱼结果。

    - 参数
      - user_id: 用户的唯一标识符
    - 返回
      - 选择的鱼的名称
      - 鱼的长度
      - 是否进行了权重调整
      - 运势星级数（如果有的话），否则为 None
    """
    fish_quality = list(fish.keys())
    fish_quality_weight = await get_weight(user_id=user_id, fish_quality=fish_quality)
    quality = random.choices(fish_quality, weights=fish_quality_weight[0])[0]

    return (
        random.choice(fish[quality]["fish"]),
        random.randint(fish[quality]["long"][0], fish[quality]["long"][1]),
        fish_quality_weight[1],
        fish_quality_weight[2],
    )


def get_quality(fish_name: str) -> str:
    """获取鱼的品质"""
    for quality in fish:
        if fish_name in fish[quality]["fish"]:
            return quality
    raise ValueError(f"未知的鱼：{fish_name}")


def get_price(fish_name: str, fish_long: int) -> float:
    """获取鱼的价格"""
    for quality in fish:
        if fish_name in fish[quality]["fish"]:
            return fish[quality]["price_mpr"] * fish_long
    raise ValueError(f"未知的鱼：{fish_name}")


async def save_fish(user_id: str, fish_name: str, fish_long: int) -> None:
    """向数据库写入鱼以持久化保存"""
    time_now = int(time.time())
    fishing_limit = config.fishing_limit

    async with get_session() as session:
        stmt = select(FishingRecord).where(FishingRecord.user_id == user_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            loads_fishes: dict[str, list[int]] = json.loads(record.fishes)
            try:
                loads_fishes[fish_name].append(fish_long)
            except KeyError:
                loads_fishes[fish_name] = [fish_long]
            dump_fishes = json.dumps(loads_fishes)
            record.time = time_now + fishing_limit
            record.frequency += 1
            record.fishes = dump_fishes
            await session.commit()
        else:
            data = {fish_name: [fish_long]}
            dump_fishes = json.dumps(data)
            new_record = FishingRecord(
                user_id=user_id,
                time=time_now + fishing_limit,
                frequency=1,
                fishes=dump_fishes,
            )
            session.add(new_record)
            await session.commit()


async def get_stats(user_id: str) -> str:
    """获取钓鱼统计信息（总长度，次数，次元币总数）"""
    async with get_session() as session:
        stmt = select(FishingRecord).where(FishingRecord.user_id == user_id)
        result = await session.execute(stmt)
        fishing_record = result.scalar_one_or_none()

        if fishing_record:
            total_length = sum(
                sum(fish_long)
                for fish_long in json.loads(fishing_record.fishes).values()
            )  # 查询金币插件的历史总金币
            count_coin = await get_count_coin(user_id)
            return (
                f"共钓到鱼次数 {fishing_record.frequency} 次\n"
                f"背包内鱼总长度 {total_length}cm\n"
                f"总共获得过 {count_coin} {fishing_coin_name}"
            )
        return "你还没有钓过鱼，快去钓鱼吧"


async def get_backpack(user_id: str) -> str | list:
    """从数据库查询背包内容"""
    async with get_session() as session:
        stmt = select(FishingRecord).where(FishingRecord.user_id == user_id)
        result = await session.execute(stmt)
        fishes_record = result.scalar_one_or_none()

        if fishes_record:
            load_fishes = json.loads(fishes_record.fishes)
            if not load_fishes:
                return "你的背包里空无一物"

            sorted_fishes = {
                quality: {
                    fish_name: fish_info
                    for fish_name, fish_info in load_fishes.items()
                    if get_quality(fish_name) == quality
                }
                for quality in [
                    "腐烂",
                    "发霉",
                    "普通",
                    "金",
                    "虚空",
                    "隐火",
                ]
            }
            backpack_list = []
            for quality, fishes in sorted_fishes.items():
                if fishes:
                    quality_list = [f"{quality} 鱼:"]
                    quality_list.extend(
                        f"  {fish_name}:\n    个数: {len(fish_info)}\n    总长度: {sum(fish_info)}"
                        for fish_name, fish_info in fishes.items()
                    )
                    backpack_list.append("\n".join(quality_list))
            return backpack_list or "你的背包里空无一物"
        return "你的背包里空无一物"


async def sell_quality_fish(user_id: str, quality: str) -> str:
    """卖出指定品质的鱼"""
    async with get_session() as session:
        stmt = select(FishingRecord).where(FishingRecord.user_id == user_id)
        result = await session.execute(stmt)
        fishes_record = result.scalar_one_or_none()

        if fishes_record:
            load_fishes = json.loads(fishes_record.fishes)
            if not load_fishes:
                return "你的背包里空无一物"
            if quality not in [get_quality(fish_name) for fish_name in load_fishes]:
                return f"你的背包里没有 {quality} 鱼了"
            price = sum(
                round(get_price(fish_name, sum(fish_long)), 2)
                for fish_name, fish_long in load_fishes.items()
                if get_quality(fish_name) == quality
            )
            await add_coin(user_id, price)
            load_fishes = {
                fish_name: fish_long
                for fish_name, fish_long in load_fishes.items()
                if get_quality(fish_name) != quality
            }
            dump_fishes = json.dumps(load_fishes)

            stmt = (
                update(FishingRecord)
                .where(FishingRecord.user_id == user_id)
                .values(fishes=dump_fishes)
            )
            await session.execute(stmt)
            await session.commit()
            return f"你卖出了所有 {quality} 鱼，获得了 {price} {fishing_coin_name}"
        return "你的背包里空无一物"


async def sell_all_fish(user_id: str) -> str:
    """卖出所有鱼"""
    async with get_session() as session:
        stmt = select(FishingRecord).where(FishingRecord.user_id == user_id)
        result = await session.execute(stmt)
        fishes_record = result.scalar_one_or_none()

        if fishes_record:
            load_fishes = json.loads(fishes_record.fishes)
            if not load_fishes:
                return "你的背包里空无一物"
            price = sum(
                round(get_price(fish_name, sum(fish_long)), 2)
                for fish_name, fish_long in load_fishes.items()
            )
            # 使用金币插件接口
            await add_coin(user_id, price)
            stmt = (
                update(FishingRecord)
                .where(FishingRecord.user_id == user_id)
                .values(fishes="{}")
            )
            await session.execute(stmt)
            await session.commit()
            return f"你卖出了所有鱼，获得了 {price} {fishing_coin_name}"
        return "你的背包里空无一物"


async def sell_fish(user_id: str, fish_name: str) -> str:
    """
    卖鱼 (一次性卖完)

    参数：
        - user_id: 将要卖鱼的用户唯一标识符，用于区分谁正在卖鱼
        - fish_name: 将要卖鱼的鱼名称

    返回：
        - (str): 待回复的文本
    """
    async with get_session() as session:
        stmt = select(FishingRecord).where(FishingRecord.user_id == user_id)
        result = await session.execute(stmt)
        fishes_record = result.scalar_one_or_none()

        if fishes_record:
            load_fishes = json.loads(fishes_record.fishes)
            if fish_name not in load_fishes:
                return "你的背包里没有这种鱼"
            fish_long = load_fishes[fish_name]
            price = round(get_price(fish_name, sum(fish_long)), 2)
            # 更新金币
            await add_coin(user_id, price)
            del load_fishes[fish_name]
            dump_fishes = json.dumps(load_fishes)

            stmt = (
                update(FishingRecord)
                .where(FishingRecord.user_id == user_id)
                .values(fishes=dump_fishes)
            )
            await session.execute(stmt)
            await session.commit()
            return f"你卖出了 {fish_name}×{len(fish_long)}，获得了 {price} {fishing_coin_name}"
        return "你的背包里空无一物"


async def get_balance(user_id: str) -> str:
    """获取余额"""
    coin = await get_coin(user_id)
    return f"你有 {coin} {fishing_coin_name}" if coin else "你什么也没有 :)"


async def switch_fish(event: GroupMessageEvent | PrivateMessageEvent) -> bool:
    """钓鱼开关切换，没有就创建"""
    if isinstance(event, PrivateMessageEvent):
        return True

    async with get_session() as session:
        stmt = select(FishingSwitch).where(FishingSwitch.group_id == event.group_id)
        result = await session.execute(stmt)
        switch = result.scalar_one_or_none()

        if switch:
            switch.switch = not switch.switch
            await session.commit()
            return switch.switch
        else:
            new_switch = FishingSwitch(group_id=event.group_id, switch=False)
            session.add(new_switch)
            await session.commit()
            return False


async def get_switch_fish(event: GroupMessageEvent | PrivateMessageEvent) -> bool:
    """获取钓鱼开关"""
    if isinstance(event, PrivateMessageEvent):
        return True

    async with get_session() as session:
        stmt = select(FishingSwitch).where(FishingSwitch.group_id == event.group_id)
        result = await session.execute(stmt)
        switch = result.scalar_one_or_none()

        return switch.switch if switch else True
