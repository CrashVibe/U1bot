from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment

require("nonebot_plugin_orm")
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .models import WaifuRelationship
from .utils import bbcode_to_png

cp_list = on_command("本群CP", block=True)


@cp_list.handle()
async def show_cp_list(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id

    async with get_session() as session:
        # 获取CP数据
        cp_stmt = select(WaifuRelationship).where(
            WaifuRelationship.group_id == group_id
        )
        cp_result = await session.execute(cp_stmt)
        relationships = cp_result.fetchall()

        # 生成消息内容
        content = "[size=40][b]本群CP列表[/b][/size]\n"
        content += "────────────────\n"

        if not relationships:
            content += "暂无CP记录"
        else:
            for relationship_tuple in relationships:
                relationship = relationship_tuple[0]
                user_id = relationship.user_id
                partner_id = relationship.partner_id

                try:
                    user = await bot.get_group_member_info(
                        group_id=group_id, user_id=user_id
                    )
                    partner = await bot.get_group_member_info(
                        group_id=group_id, user_id=partner_id
                    )
                    content += f"❤ {user['card'] or user['nickname']} ↔ {partner['card'] or partner['nickname']}\n"
                except Exception:
                    # 如果用户不在群里了，跳过
                    continue

    # 生成图片
    img_bytes = bbcode_to_png(content)
    await cp_list.finish(MessageSegment.image(img_bytes))
