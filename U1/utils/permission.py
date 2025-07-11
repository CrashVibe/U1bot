from nonebot.adapters.milky.event import GroupMessageEvent
from nonebot.adapters.milky.model.common import Member
from nonebot.permission import Permission


async def _group_admin(event: GroupMessageEvent) -> bool:
    if isinstance(event.data.sender, Member):
        return event.data.sender.role == "admin"
    raise TypeError(
        f"Expected Member, got {type(event.data.sender)}: {event.data.sender}"
    )


async def _group_owner(event: GroupMessageEvent) -> bool:
    if isinstance(event.data.sender, Member):
        return event.data.sender.role == "owner"
    raise TypeError(
        f"Expected Member, got {type(event.data.sender)}: {event.data.sender}"
    )


async def _group_member(event: GroupMessageEvent) -> bool:
    if isinstance(event.data.sender, Member):
        return event.data.sender.role == "member"
    raise TypeError(
        f"Expected Member, got {type(event.data.sender)}: {event.data.sender}"
    )


GROUP_MEMBER: Permission = Permission(_group_member)
"""匹配任意群员群聊消息类型事件"""
GROUP_ADMIN: Permission = Permission(_group_admin)
"""匹配任意群管理员群聊消息类型事件"""
GROUP_OWNER: Permission = Permission(_group_owner)
"""匹配任意群主群聊消息类型事件"""
