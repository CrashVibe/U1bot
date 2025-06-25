"""今日运势插件的数据源，供其他插件调用"""

import random
import time
from datetime import datetime
from os import path
from pathlib import Path
from zoneinfo import ZoneInfo

import aiofiles
import ujson as json
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import MemberData

luckpath = Path(path.join(path.dirname(__file__), "Fortune.json"))


async def get_user_luck_star(user_id: str) -> int | None:
    """
    获取用户今日的运势星级数。

    参数:
        user_id: 用户ID

    返回:
        int | None: 运势星级数（0-7），如果用户今天没有运势则返回 None
    """
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
                    return luck_star_num
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing luck data: {e}")

    return None


async def get_user_luck_info(user_id: str) -> dict | None:
    """
    获取用户今日的完整运势信息。

    参数:
        user_id: 用户ID

    返回:
        dict | None: 运势信息字典，包含运势、星级、签文、解签等，如果用户今天没有运势则返回 None
    """
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
                    luck_info = luckdata.get(str(luck.luckid))
                    if luck_info:
                        return {
                            "luckid": luck.luckid,
                            "star_count": luck_info.get("星级", "").count("★"),
                            "fortune": luck_info.get("运势", ""),
                            "star_level": luck_info.get("星级", ""),
                            "poem": luck_info.get("签文", ""),
                            "explanation": luck_info.get("解签", ""),
                        }
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing luck data: {e}")

    return None


async def luck_result(user_id: str, focus: bool = False) -> str:
    """
    获取用户的运势结果，包含完整的数据库操作逻辑。

    参数:
        user_id: 用户ID
        focus: 是否强制重新生成运势

    返回:
        str: 格式化的运势文本
    """
    # 加载运势数据
    async with aiofiles.open(luckpath, encoding="utf-8") as f:
        luckdata = json.loads(await f.read())

    async with get_session() as session:
        # 读取数据库
        stmt = select(MemberData).where(MemberData.user_id == user_id)
        result = await session.execute(stmt)
        member_model = result.scalar_one_or_none()

        if member_model is None:
            # 如果没有数据则创建数据
            luck_result_text, luckid = random_luck(luckdata)
            member_model = MemberData(
                user_id=user_id,
                luckid=luckid,
                time=datetime.now(ZoneInfo("Asia/Shanghai")),
            )
            session.add(member_model)
            await session.commit()
            return luck_result_text
        elif (
            member_model.time.strftime("%Y-%m-%d") == time.strftime("%Y-%m-%d")
            and not focus
        ):
            # 如果是今天的数据则返回今天的数据
            r = str(member_model.luckid)
            result_text = (
                f"----\n{luckdata[r]['运势']}\n{luckdata[r]['星级']}\n"
                f"{luckdata[r]['签文']}\n{luckdata[r]['解签']}\n----"
            )
            return result_text
        else:
            # 如果不是今天的数据则随机运势
            result_text, luckid = random_luck(luckdata)
            member_model.luckid = luckid
            member_model.time = datetime.now(ZoneInfo("Asia/Shanghai"))
            session.add(member_model)
            await session.commit()
            return result_text


def random_luck(luckdata: dict):
    """
    随机获取运势信息。

    参数:
        luckdata: 运势数据字典

    返回:
        tuple: 运势信息和选择的运势编号。
    """
    # 判断是否有在 json 文件中和是否有 time 键值
    r = random.choice(list(luckdata.keys()))
    if datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m-%d") == "01-01":
        r = "67"
    result_text = (
        f"----\n{luckdata[r]['运势']}\n{luckdata[r]['星级']}\n"
        f"{luckdata[r]['签文']}\n{luckdata[r]['解签']}\n----"
    )
    return result_text, int(r)


async def create_or_update_luck(user_id: str, luckid: int) -> None:
    """
    创建或更新用户的运势数据。

    参数:
        user_id: 用户ID
        luckid: 运势ID
    """
    async with get_session() as session:
        stmt = select(MemberData).where(MemberData.user_id == user_id)
        result = await session.execute(stmt)
        member_model = result.scalar_one_or_none()

        if member_model is None:
            # 创建新记录
            member_model = MemberData(
                user_id=user_id,
                luckid=luckid,
                time=datetime.now(ZoneInfo("Asia/Shanghai")),
            )
            session.add(member_model)
        else:
            # 更新现有记录
            member_model.luckid = luckid
            member_model.time = datetime.now(ZoneInfo("Asia/Shanghai"))

        await session.commit()


async def get_user_luck_raw(user_id: str) -> MemberData | None:
    """
    获取用户的原始运势数据库记录。

    参数:
        user_id: 用户ID

    返回:
        MemberData | None: 用户的运势记录，如果不存在则返回 None
    """
    async with get_session() as session:
        stmt = select(MemberData).where(MemberData.user_id == user_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
