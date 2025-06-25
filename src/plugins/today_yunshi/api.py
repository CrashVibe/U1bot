"""今日运势插件的 API 接口，供其他插件调用"""

import time
from os import path
from pathlib import Path

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
