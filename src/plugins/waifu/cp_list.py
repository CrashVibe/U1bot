from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment

require("nonebot_plugin_orm")
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import PWaifu, WaifuCP
from .utils import bbcode_to_png, get_bi_mapping

cp_list = on_command("本群CP", block=True)


@cp_list.handle()
async def show_cp_list(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    async with get_session() as session:
        # 获取CP数据
        cp_stmt = select(WaifuCP).where(WaifuCP.group_id == group_id)
        cp_result = await session.execute(cp_stmt)
        cp_data = cp_result.scalar_one_or_none()

        waifu_stmt = select(PWaifu).where(PWaifu.group_id == group_id)
        waifu_result = await session.execute(waifu_stmt)
        waifu_data = waifu_result.scalar_one_or_none()

        # 生成消息内容
        content = "[size=40][b]本群CP列表[/b][/size]\n"
        content += "────────────────\n"

        if not cp_data or not waifu_data:
            content += "暂无CP记录"
        else:
            seen = set()
            for waifu_id in waifu_data.waifu_list:
                if (
                    user_id := get_bi_mapping(cp_data.affect, waifu_id)
                ) and user_id not in seen:
                    user = await bot.get_group_member_info(
                        group_id=group_id, user_id=user_id
                    )
                    waifu = await bot.get_group_member_info(
                        group_id=group_id, user_id=waifu_id
                    )
                content += f"❤ {user['card']} ↔ {waifu['card']}\n"
                seen.update([user_id, waifu_id])

    # 生成图片
    img_bytes = bbcode_to_png(content)
    await cp_list.finish(MessageSegment.image(img_bytes))
