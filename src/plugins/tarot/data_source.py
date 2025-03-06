import asyncio
import random
from io import BytesIO
from pathlib import Path

import aiofiles
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    PrivateMessageEvent,
)
from nonebot.matcher import Matcher
from PIL import Image

from .config import EventNotSupport, ResourceError, get_tarot, tarot_config

try:
    import ujson as json
except ModuleNotFoundError:
    import json


def chain_reply(
    bot: Bot,
    chain: list[dict[str, str | dict[str, str | MessageSegment]]],
    msg: MessageSegment | Message,
) -> list[dict[str, str | dict[str, str | MessageSegment]]]:
    data = {
        "type": "node",
        "data": {
            "name": next(iter(tarot_config.nickname)),
            "uin": bot.self_id,
            "content": msg,
        },
    }
    chain.append(data)
    return chain


def pick_theme() -> str:
    """
    Random choose a theme from the union of local & official themes
    """
    if sub_themes_dir := [
        f.name for f in tarot_config.tarot_path.iterdir() if f.is_dir()
    ]:
        return random.choice(
            list(set(sub_themes_dir).union(tarot_config.tarot_official_themes))
        )

    return random.choice(tarot_config.tarot_official_themes)


def pick_sub_types(theme: str) -> list[str]:
    """
    Random choose a sub type of the "theme".
    If it is in official themes, all the sub types are available.
    """
    all_sub_types: list[str] = ["MajorArcana", "Cups", "Pentacles", "Sowrds", "Wands"]

    if theme == "BilibiliTarot":
        return all_sub_types

    if theme == "TouhouTarot":
        return ["MajorArcana"]

    sub_types: list[str] = [
        f.name
        for f in (tarot_config.tarot_path / theme).iterdir()
        if f.is_dir() and f.name in all_sub_types
    ]

    return sub_types


class Tarot:
    def __init__(self):
        self.tarot_json: Path = Path(__file__).parent / "tarot.json"
        self.is_chain_reply: bool = tarot_config.chain_reply

    async def divine(self, bot: Bot, matcher: Matcher, event: Event) -> None:
        """
        General tarot devination.
        1. Choose a theme
        2. Open tarot.json and Random choose a formation
        3. Get the devined cards list and their text
        4. Generate message (or chain reply if enabled)
        """
        # 1. Pick a theme randomly
        theme: str = pick_theme()

        async with aiofiles.open(self.tarot_json, encoding="utf-8") as f:
            content = json.loads(await f.read())
            all_cards = content.get("cards")
            all_formations = content.get("formations")

            formation_name = random.choice(list(all_formations))
            formation = all_formations.get(formation_name)

        await matcher.send(f"启用{formation_name}，正在洗牌中")

        # 2. Get cards of "cards_num"
        cards_num: int = formation.get("cards_num")
        cards_info_list = self._random_cards(all_cards, theme, cards_num)

        # 3. Get the text of representations
        is_cut: bool = formation.get("is_cut")
        representations: list[str | list[str]] = random.choice(
            formation.get("representations")
        )

        # 4. Genrate message
        chain = []
        for i, card_info in enumerate(cards_info_list):
            # Select the #i tarot
            msg_header = MessageSegment.text(
                f"{'切牌' if is_cut and i == cards_num - 1 else f'第{i + 1}张牌'}「{representations[i]}」\n"
            )

            flag, msg_body = await self._get_text_and_image(theme, card_info)
            if not flag:
                await matcher.finish(msg_body)

            if (
                isinstance(event, GroupMessageEvent | PrivateMessageEvent)
            ) and self.is_chain_reply:
                chain = chain_reply(bot, chain, msg_header + msg_body)
            elif isinstance(event, PrivateMessageEvent):
                await matcher.send(msg_header + msg_body)
            elif isinstance(event, GroupMessageEvent):
                await matcher.send(msg_header + msg_body)
                if i < cards_num - 1:
                    await asyncio.sleep(1)  # In case of frequency sending
            else:
                raise EventNotSupport

        if self.is_chain_reply:
            if isinstance(event, PrivateMessageEvent):
                await bot.send_private_forward_msg(
                    user_id=int(event.get_user_id()), messages=chain
                )
            elif isinstance(event, GroupMessageEvent):
                await bot.send_group_forward_msg(
                    group_id=event.group_id, messages=chain
                )

    async def onetime_divine(self) -> MessageSegment | str | Message:
        """
        One-time divination.
        """
        # 1. Pick a theme randomly
        theme: str = pick_theme()

        # 2. Get one card ONLY
        async with aiofiles.open(self.tarot_json, encoding="utf-8") as f:
            content = json.loads(await f.read())
            all_cards = content.get("cards")
            card_info_list = self._random_cards(all_cards, theme)

        # 3. Get the text and image
        flag, body = await self._get_text_and_image(theme, card_info_list[0])

        return MessageSegment.text("回应是") + body if flag else body

    def switch_chain_reply(self, new_state: bool) -> None:
        """
        开启/关闭全局群聊转发模式
        """
        self.is_chain_reply = new_state

    def _random_cards(
        self,
        all_cards: dict[str, dict[str, str | dict[str, str]]],
        theme: str,
        num: int = 1,
    ) -> list[dict[str, str | dict[str, str]]]:
        """
        Iterate the sub directory, get the subset of cards
        """
        sub_types: list[str] = pick_sub_types(theme)

        if not sub_types:
            raise ResourceError(f"本地塔罗牌主题 {theme} 为空！请检查资源！")

        subset: dict[str, dict[str, str | dict[str, str]]] = {
            k: v for k, v in all_cards.items() if v.get("type") in sub_types
        }

        # 2. Random sample the cards according to the num
        cards_index: list[str] = random.sample(list(subset), num)
        cards_info: list[dict[str, str | dict[str, str]]] = [
            v for k, v in subset.items() if k in cards_index
        ]

        return cards_info

    async def _get_text_and_image(
        self, theme: str, card_info: dict[str, str | dict[str, str]]
    ) -> tuple[bool, Message | MessageSegment]:
        """
        Get a tarot image & text arrcording to the "card_info"
        """
        _type = card_info.get("type")
        _name = card_info.get("pic")
        if not isinstance(_name, str) or not isinstance(_type, str):
            raise ResourceError(
                f"Tarot image {theme}/{_type}/{_name} doesn't exist! Make sure the type {_type} is complete."
            )
        img_name: str = ""
        img_dir: Path = tarot_config.tarot_path / theme / _type

        # Consider the suffix of pictures
        for p in img_dir.glob(f"{_name}.*"):
            img_name = p.name

        if img_name == "":
            if theme not in tarot_config.tarot_official_themes:
                # In user's theme, then raise ResourceError
                raise ResourceError(
                    f"Tarot image {theme}/{_type}/{_name} doesn't exist! Make sure the type {_type} is complete."
                )
            data = await get_tarot(theme, _type, _name)
            if data is None:
                return False, MessageSegment.text(
                    "图片下载出错，请重试或将资源部署本地……"
                )

            img: Image.Image = Image.open(BytesIO(data))
        else:
            img: Image.Image = Image.open(img_dir / img_name)

        # 3. Choose up or down
        name_cn = card_info.get("name_cn")
        if not isinstance(name_cn, str):
            raise ResourceError(f"Invalid name_cn value: {name_cn}")
        if random.random() < 0.5:
            # 正位
            meaning = card_info.get("meaning")
            if not isinstance(meaning, dict):
                raise ResourceError(f"Invalid meaning value: {meaning}")
            meaning = meaning.get("up")
            msg = MessageSegment.text(f"「{name_cn}正位」「{meaning}」\n")
        else:
            meaning = card_info.get("meaning")
            if not isinstance(meaning, dict):
                raise ResourceError(f"Invalid meaning value: {meaning}")
            meaning = meaning.get("down")
            msg = MessageSegment.text(f"「{name_cn}逆位」「{meaning}」\n")
            img = img.rotate(180)

        buf = BytesIO()
        img.save(buf, format="png")

        return True, msg + MessageSegment.image(buf)


tarot_manager = Tarot()
