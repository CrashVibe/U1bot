from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg

require("nonebot_plugin_orm")
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import YinpaActive, YinpaPassive
from .utils import bbcode_to_png, get_message_at

record = on_command("涩涩记录", block=True)


@record.handle()
async def show_yinpa_record(
    bot: Bot, event: GroupMessageEvent, arg: Message = CommandArg()
):
    # 获取目标用户
    if targets := get_message_at(arg):
        user_id = targets[0]
    else:
        user_id = event.user_id

    async with get_session() as session:
        # 查询记录
        active_stmt = select(YinpaActive).where(YinpaActive.user_id == user_id)
        active_result = await session.execute(active_stmt)
        active = active_result.scalar_one_or_none()

        passive_stmt = select(YinpaPassive).where(YinpaPassive.user_id == user_id)
        passive_result = await session.execute(passive_stmt)
        passive = passive_result.scalar_one_or_none()

        # 生成BBCode
        content = f"[size=24][b]@{user_id} 的涩涩记录[/b][/size]\n"
        content += "────────────────\n"
        content += f"主动出击次数：{active.active_count if active else 0}\n"
        content += f"被透次数：{passive.passive_count if passive else 0}\n"
        content += f"最后更新时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')}"

        # 生成图片
    img_bytes = bbcode_to_png(content)
    await record.finish(MessageSegment.image(img_bytes))
