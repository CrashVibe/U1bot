from io import BytesIO
from pathlib import Path

from nonebot.adapters.onebot.v11.message import Message, MessageSegment


class MessageBuilder(Message):
    def at(self, user_id: int | str) -> "MessageBuilder":
        self.append(MessageSegment.at(user_id))
        return self

    def face(self, id_: int) -> "MessageBuilder":
        self.append(MessageSegment.face(id_))
        return self

    def image(
        self,
        file: str | bytes | BytesIO | Path,
        type_: str | None = None,
        cache: bool = True,
        proxy: bool = True,
        timeout: int | None = None,
    ) -> "MessageBuilder":
        self.append(MessageSegment.image(file, type_, cache, proxy, timeout))
        return self

    def reply(self, id_: int) -> "MessageBuilder":
        self.append(MessageSegment.reply(id_))
        return self

    def text(self, text: str) -> "MessageBuilder":
        if self[-1].type == "text":
            text = "\n" + text
        self.append(MessageSegment.text(text))
        return self

    def done(self) -> str:
        return "".join(map(str, self))
