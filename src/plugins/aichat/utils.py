import re

import ujson as json
from nonebot import logger
from nonebot.adapters.onebot.v11.event import MessageEvent, Reply
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageToolCall

from ..today_yunshi import luck_result
from .config import Config, ai_config

tools: list = [
    {
        "type": "function",
        "function": {
            "name": "random_fortune",
            "description": "重新生成对应QQ号的用户的运势，你需要对运势内容进行解读",
            "parameters": {
                "type": "object",
                "properties": {
                    "num": {
                        "type": "string",
                        "description": "用户的 QQ 号码，例如 123456789。",
                    }
                },
                "required": ["num"],
            },
        },
    },
]


client = AsyncOpenAI(
    api_key=ai_config.api_key,
    base_url=ai_config.base_url,
)


async def chat_with_gpt(
    data: list, config: Config = ai_config
) -> ChatCompletionMessage:
    result = await client.chat.completions.create(
        model=config.appoint_model,
        temperature=config.temperature,
        messages=data,
        top_p=0.3,
        frequency_penalty=1,
        presence_penalty=0,
        tools=tools,
    )
    return result.choices[0].message


async def get_intent(message: str, botid: str, config: Config = ai_config) -> bool:
    result = await client.chat.completions.create(
        model=config.appoint_model,
        messages=[
            {
                "role": "system",
                "content": f"你是一个助手，你自己的消息ID是({botid})，根据群聊对话情感判断是否该回复群聊中的消息，注意如果对方还有讲话的意图就不需要回复。",
            },
            {
                "role": "user",
                "content": f"判断以下消息的意图，并回复'需要回复'或'不需要回复': {message}",
            },
        ],
    )
    logger.info(f"意图判断：{result.choices[0].message.content!s}")
    return "需要回复" in str(result.choices[0].message.content)


async def call_tools(tool_calls: ChatCompletionMessageToolCall) -> dict | None:
    logger.info(f"工具调用：{tool_calls}")
    if tool_calls.type == "function":
        function_call = tool_calls.function

        # 验证调用的函数名是否正确
        if function_call.name == "random_fortune":
            try:
                # 解析调用的参数
                arguments = json.loads(function_call.arguments)

                # 验证参数是否包含QQ号
                if "num" in arguments:
                    qq_number = int(arguments["num"])
                    result = await luck_result(qq_number, True)
                    return {
                        "role": "tool",
                        "tool_call_id": tool_calls.id,
                        "content": result,
                    }
                else:
                    logger.error("错误：QQ号是必需的。")
            except json.JSONDecodeError:
                logger.error("错误：参数的JSON格式无效。")
        else:
            logger.error("错误：函数名不匹配。")


def extract_image_url(message: str) -> tuple[bool, str]:
    """
    从消息文本中提取图片 URL。
    Args:
    - message (str): 消息文本。

    Returns:
    - tuple: 包含两个元素：
        - is_image (bool): 是否找到图片 URL。
        - image_url (str): 图片 URL。
    """
    url_pattern = r"url=(https?[^,]+)"
    if image_match := re.search(url_pattern, message):
        return True, image_match[1]

    url_pattern = r"url=(file[^,]+)"
    if image_match := re.search(url_pattern, message):
        return True, image_match[1]

    return False, ""


def is_image_message(data: MessageEvent | Reply, is_cq_code: bool) -> tuple[bool, str]:
    """
    判断是否是图片消息。
    Args:
    - data (MessageEvent): 消息数据。
    - is_cq_code (bool): 是否是 CQ 码。

    Returns:
    - tuple: 包含两个元素：
        - is_image (bool): 是否是图片消息。
        - image_url (str): 图片 URL。
    """
    if is_cq_code:
        return extract_image_url(str(data.message))

    for msg in data.message:
        if msg.type == "image" and (image_url := msg.data.get("url", "")):
            return True, image_url

    return False, ""


from nonebot.adapters.onebot.v11.utils import unescape


def replace_cq_with_caption(text: str, caption: str) -> str:
    """
    将文本中的 [CQ:...] 标签替换为指定的描述。

    参数:
    - text: 包含 [CQ:...] 标签的原始文本
    - caption: 用于替换 [CQ:...] 的描述文本

    返回值:
    - 替换后的文本
    """
    # 反转义
    text = unescape(text)

    # 匹配包含 URL 或 file 的 [CQ:image] 标签，处理 subType=1 结尾
    pattern = r"\[CQ:image(?:,.*?url=(https?://[^,]+|file=[^,]+).*?subType=\d+)?\]"

    # 替换匹配到的 [CQ:image] 标签
    return re.sub(pattern, f"[图片,描述:{caption}]", text)


def replace_at_message(text: str) -> str:
    """
    检测并替换指定的 CQ:at 消息。
    Args:
    - text (str): 原始消息文本。

    Returns:
    - str: 替换后的文本。
    """
    # 匹配 CQ:at 类型的消息，提取 qq 和 name
    cq_at_pattern = r"\[CQ:at,qq=(\d+),name=(.*?)\]"

    def replace_at(match):
        name = match.group(2)
        # 检查是否是指定的 qq 号
        return f"{name} "

    # 使用正则表达式进行替换，处理所有匹配项
    return re.sub(cq_at_pattern, replace_at, text)


def extract_mface_summary(text: str) -> str:
    """
    检测并提取 CQ:mface 消息的 summary 字段，返回 '表情包,描述:summary内容' 格式。
    Args:
    - text (str): 原始消息文本。

    Returns:
    - str: 提取后的描述信息，如果没有匹配，则返回空字符串。
    """
    # 匹配 CQ:mface 的消息，并提取 summary 字段
    cq_mface_pattern = r"\[CQ:mface,[^\]]*summary=\[([^\]]+)\][^\]]*\]"

    if match := re.search(cq_mface_pattern, text):
        summary = match[1]
        return f"[表情包,描述:{summary}]"

    return ""  # 如果没有匹配到，则返回空字符串
