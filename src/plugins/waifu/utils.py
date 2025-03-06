import asyncio
import hashlib
import io

import httpx
from nonebot import logger
from nonebot.adapters.onebot.v11 import Message
from pil_utils import Text2Image

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
