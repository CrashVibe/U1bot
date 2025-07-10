import base64
import re
import ssl

import aiohttp
from nonebot.adapters.milky import MessageEvent
from nonebot.adapters.milky.message import Image, IncomingImageData


async def url_to_base64(image_url) -> str:
    ssl_context = ssl.create_default_context()
    ssl_context.set_ciphers("DEFAULT:@SECLEVEL=1")  # 降低 SSL/TLS 安全等级

    async with aiohttp.ClientSession() as session:
        async with session.get(image_url, ssl=ssl_context) as response:
            image_data = await response.read()
            return base64.b64encode(image_data).decode("utf-8")


def extract_image_url(message: str) -> str:
    """
    从消息文本中提取图片 URL。
    Args:
    - message (str): 消息文本。

    Returns:
    - str: 图片 URL。
    """
    url_pattern = r"url=(https?[^,]+)"
    if image_match := re.search(url_pattern, message):
        return image_match[1]

    url_pattern = r"url=(file[^,]+)"
    if image_match := re.search(url_pattern, message):
        return image_match[1]

    return ""


def extract_base64_from_cq_codes(text: str) -> list[str]:
    """
    从文本中提取所有 [CQ:image,file=base64://...] 中的 base64 数据。

    参数:
    - text: 包含 CQ 码的文本

    返回值:
    - list[str]: 所有提取到的 base64 数据列表
    """
    base64_images = []
    # 匹配 [CQ:image,file=base64://xxxxx] 格式
    cq_pattern = r"\[CQ:image,file=base64://([^]]+)\]"
    matches = re.findall(cq_pattern, text)
    base64_images.extend(matches)

    return base64_images


def remove_cq_codes(text: str) -> str:
    """
    移除文本中的所有 CQ 码。

    参数:
    - text: 包含 CQ 码的文本

    返回值:
    - str: 移除 CQ 码后的纯文本
    """
    # 移除所有 [CQ:...] 格式的代码
    return re.sub(r"\[CQ:[^\]]+\]", "", text).strip()


async def process_image_message(data: MessageEvent) -> tuple[bool, str, list[str]]:
    """
    处理图片消息，返回是否包含图片、处理后的文本和图片base64数据。

    参数:
    - data: 消息事件数据

    返回值:
    - tuple: (是否包含图片, 处理后的文本, 图片base64数据列表)
    """
    has_image = False
    base64_images = []

    for msg in data.message:
        if isinstance(msg, Image) and msg.data is IncomingImageData:
            has_image = True
            base64_data = await url_to_base64(msg.data["temp_url"])
            base64_images.append(base64_data)

    # 移除消息中的所有 CQ 码
    clean_text = remove_cq_codes(str(data.message))

    return has_image, clean_text, base64_images
