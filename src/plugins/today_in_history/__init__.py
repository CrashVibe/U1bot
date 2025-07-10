import base64
from datetime import date

import httpx
import ujson as json
from nonebot import on_fullmatch, require
from nonebot.adapters.milky import MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot_plugin_htmlrender import text_to_pic

require("nonebot_plugin_apscheduler")

__plugin_meta__ = PluginMetadata(
    name="历史上的今天",
    description="让我们看看今天在过去都发生了什么吧!",
    usage="指令:历史上的今天",
)

history_matcher = on_fullmatch("历史上的今天")


@history_matcher.handle()
async def _():
    await history_matcher.finish(await get_history_info())


# api处理->json
def text_handle(text: str) -> dict:
    text = text.replace(r"<\/a>", "")
    text = text.replace("\n", "")

    # 去除html标签
    while True:
        address_head = text.find("<a target=")
        address_end = text.find(">", address_head)
        if address_head == -1 or address_end == -1:
            break
        text_middle = text[address_head : address_end + 1]
        text = text.replace(text_middle, "")

    # 去除api返回内容中不符合json格式的部分
    # 去除key:desc值
    address_head: int = 0
    while True:
        address_head = text.find('"desc":', address_head)
        address_end = text.find('"cover":', address_head)
        if address_head == -1 or address_end == -1:
            break
        text_middle = text[address_head + 8 : address_end - 2]
        address_head = address_end
        text = text.replace(text_middle, "")

    # 去除key:title中多引号
    address_head: int = 0
    while True:
        address_head = text.find('"title":', address_head)
        address_end = text.find('"festival"', address_head)
        if address_head == -1 or address_end == -1:
            break
        text_middle = text[address_head + 9 : address_end - 2]
        if '"' in text_middle:
            text_middle = text_middle.replace('"', " ")
            text = text[: address_head + 9] + text_middle + text[address_end - 2 :]
        address_head = address_end

    return json.loads(text)


# 信息获取
async def get_history_info() -> MessageSegment:
    async with httpx.AsyncClient() as client:
        month = date.today().strftime("%m")
        day = date.today().strftime("%d")
        url = f"https://baike.baidu.com/cms/home/eventsOnHistory/{month}.json"
        r = await client.get(url)
        if r.status_code != 200:
            return MessageSegment.text("获取失败，请重试")
        r.encoding = "unicode_escape"
        data = text_handle(r.text)
        today = f"{month}{day}"
        s = f"历史上的今天 {today}\n"
        len_max = len(data[month][month + day])
        for i in range(len_max):
            str_year = data[month][today][i]["year"]
            str_title = data[month][today][i]["title"]
            s = (
                f"{s}{str_year} {str_title}"
                if i == len_max - 1
                else f"{s}{str_year} {str_title}\n"
            )
        img_bytes = await text_to_pic(s)
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")
        return MessageSegment.image(f"base64://{img_base64}")
