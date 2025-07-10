from nonebot.adapters.milky import Message

def extract_image_urls(message: Message) -> list[str]:
    """提取消息中的图片链接

    参数:
        message: 消息对象

    返回:
        图片链接列表
    """
    return [
        segment.data["url"]
        for segment in message
        if (segment.type == "image") and ("url" in segment.data)
    ]
