import asyncio
import hashlib
import io

import httpx
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message
from pil_utils import Text2Image

from .models import WaifuProtect

defualt_md5 = "acef72340ac0e914090bd35799f5594e"


async def download_avatar(user_id: int) -> bytes:
    url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
    data = await download_url(url)
    if hashlib.md5(data, usedforsecurity=False).hexdigest() == defualt_md5:
        url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100"
        data = await download_url(url)
    return data


async def download_url(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            try:
                resp = await client.get(url, timeout=20)
                resp.raise_for_status()
                return resp.content
            except Exception:
                await asyncio.sleep(3)
    raise Exception(f"{url} 下载失败！")


async def user_img(user_id: int) -> str:
    """获取用户头像url"""
    url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
    data = await download_url(url)
    if hashlib.md5(data, usedforsecurity=False).hexdigest() == defualt_md5:
        url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100"
    logger.info(f"头像url: {url}")
    return url


def text_to_png(msg):
    """文字转png"""
    output = io.BytesIO()
    Text2Image.from_text(msg, 50).to_image(bg_color="white", padding=(20, 20)).save(
        output, format="png"
    )
    return output


def bbcode_to_png(msg, spacing: int = 10):
    """bbcode文字转png"""
    output = io.BytesIO()
    Text2Image.from_bbcode_text(msg, 50).to_image(
        bg_color="white", padding=(20, 20)
    ).save(output, format="png")
    return output


def get_message_at(message: Message) -> list:
    """获取at列表"""
    return [int(msg.data["qq"]) for msg in message if msg.type == "at"]


def get_bi_mapping(data, input_value: int) -> None | int:
    """获取双向映射的值"""
    k_to_v = {str(k): str(v) for k, v in data.items()}  # k -> v
    v_to_k = {str(v): str(k) for k, v in data.items()}  # v -> k

    if str(input_value) in k_to_v:
        return int(k_to_v[str(input_value)])
    elif str(input_value) in v_to_k:
        return int(v_to_k[str(input_value)])
    else:
        return None


def get_bi_mapping_contains(data: dict, input_value: int) -> bool:
    """检查值是否在字典的键或值中"""
    input_str = str(input_value)

    # 使用双向映射，检查键或值是否存在
    k_to_v = {str(k): str(v) for k, v in data.items()}  # k -> v
    v_to_k = {str(v): str(k) for k, v in data.items()}  # v -> k

    # 判断是否在键或值中
    return input_str in k_to_v or input_str in v_to_k


async def get_protected_users(group_id: int) -> list[int]:
    from nonebot import require

    require("nonebot_plugin_orm")
    from nonebot_plugin_orm import get_session
    from sqlalchemy import select

    async with get_session() as session:
        stmt = select(WaifuProtect).where(WaifuProtect.group_id == group_id)
        result = await session.execute(stmt)
        protect = result.scalar_one_or_none()
        return protect.user_ids if protect else []
