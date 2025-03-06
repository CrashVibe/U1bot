from datetime import datetime

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment

from .utils import bbcode_to_png

card_pool = on_command("群友卡池", aliases={"可娶列表"}, block=True)


@card_pool.handle()
async def show_card_pool(bot: Bot, event: GroupMessageEvent):
    group_id = event.group_id
    members = await bot.get_group_member_list(group_id=group_id)

    # 按最后发言时间排序（假设活跃度）
    sorted_members = sorted(
        members, key=lambda m: m.get("last_sent_time", 0), reverse=True
    )

    # 生成BBCode内容
    content = "[size=24][b]群友卡池（按活跃度排序）[/b][/size]\n"
    content += "────────────────\n"
    for idx, member in enumerate(sorted_members[:20], 1):
        name = member["card"] or member["nickname"]
        last_active = datetime.fromtimestamp(member.get("last_sent_time", 0)).strftime(
            "%Y-%m-%d"
        )
        content += f"{idx}. {name} (最后活跃：{last_active})\n"

    # 生成图片
    img_bytes = bbcode_to_png(content)
    await card_pool.finish(MessageSegment.image(img_bytes))
