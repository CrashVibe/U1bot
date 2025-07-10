import random

from nonebot import get_driver, logger, on_command
from nonebot.adapters.milky import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.adapters.milky.event import FriendMessageEvent
from nonebot.adapters.milky.message import OutgoingForwardedMessage
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_orm import get_session
from sqlalchemy import delete, select

from U1.utils.utils import extract_image_urls

from ..coin.api import subtract_coin
from .models import cave_models
from .tool import process_image_message

nickname_list = list(get_driver().config.nickname)
Bot_NICKNAME = nickname_list[0] if nickname_list else "bot"
__plugin_meta__ = PluginMetadata(
    name="回声洞",
    description="看看别人的投稿，也可以自己投稿",
    usage="""投稿 (消耗200次元币)
匿名投稿 (消耗400次元币)
查看回声洞记录
删除 [序号]
回声洞 [序号]

示例:
投稿 今天天气真不错
匿名投稿 分享一个小秘密
删除 1
回声洞 1""",
)


cave_main = on_command("回声洞", block=True)
cave_add = on_command("投稿", aliases={"回声洞投稿"}, block=True)
cave_am_add = on_command("匿名投稿", aliases={"回声洞匿名投稿"}, block=True)
cave_history = on_command("查看回声洞记录", aliases={"回声洞记录"}, block=True)
cave_del = on_command("删除", block=True)

cave_update = on_command("更新回声洞", permission=SUPERUSER, block=True)
SUPERUSER_list = list(get_driver().config.superusers)


@cave_update.handle()
async def _():
    "操作数据库，将id重新排列，并且自动id更新到最新"
    async with get_session() as session:
        # 获取所有记录
        stmt = select(cave_models)
        result = await session.execute(stmt)
        all_caves = result.scalars().all()

        # 使用集合来跟踪已处理的详情
        seen_details = set()
        new_caves = []

        # 遍历所有对象，移除重复项
        for cave in all_caves:
            if cave.details not in seen_details:
                seen_details.add(cave.details)
                new_caves.append(cave)

        # 提示信息
        await cave_update.send(
            f"共有 {len(all_caves)} 条记录，{len(new_caves)} 条不重复记录"
        )

        # 删除所有记录
        await session.execute(delete(cave_models))

        # 保存新的对象
        for index, cave in enumerate(new_caves, start=1):
            new_cave = cave_models(
                id=index, details=cave.details, user_id=cave.user_id, time=cave.time
            )
            session.add(new_cave)
        await session.commit()

        # 重新获取所有记录
        stmt = select(cave_models)
        result = await session.execute(stmt)
        all_caves = result.scalars().all()

        new_cave = []
        # 重新排列并创建新的对象
        for cave in all_caves:
            details = cave.details
            user_id = cave.user_id
            time = cave.time
            anonymous = cave.anonymous
            new_cave.append((details, user_id, time, anonymous))

        # 按照time排序
        new_cave = sorted(new_cave, key=lambda x: x[2], reverse=False)

        # 删除所有记录
        await session.execute(delete(cave_models))

        # 重新创建排序后的记录
        for index, (details, user_id, time, anonymous) in enumerate(new_cave, start=1):
            sorted_cave = cave_models(
                id=index,
                details=details,
                user_id=user_id,
                time=time,
                anonymous=anonymous,
            )
            session.add(sorted_cave)
        await session.commit()

    await cave_update.finish("回声洞更新完成")


async def condition(event: MessageEvent, key: str) -> tuple[bool, str | None]:
    "判断是否符合投稿条件"
    urllist = extract_image_urls(event.get_message())
    if len(urllist) > 1:
        return False, "呃，投稿只能包含一张图片诶~\n再斟酌一下你的投稿内容吧~"
    if not isinstance(event, FriendMessageEvent):
        return False, "还是请来私聊我投稿罢~"
    if not key:
        return (
            False,
            "你输入了什么？一个......空气？\n请在投稿内容前加上“投稿”或“匿名投稿”",
        )
    if len(key) < 6:
        return False, "太短了罢~\n投稿内容至少需要6个字符，不要吝啬你的字数哦~"
    return True, None


@cave_add.handle()
async def _(bot: Bot, event: MessageEvent):
    has_image, clean_text, base64_images = await process_image_message(event)
    details = clean_text if has_image else str(event.get_message())
    details = details.replace("投稿", "", 1).strip()
    result = await condition(event, details)
    if result[0] is False:  # 审核
        await cave_add.finish(result[1])

    # 扣除次元币
    user_id = event.data.sender_id
    success, remaining_coin = await subtract_coin(str(user_id), 200)
    if not success:
        await cave_add.finish(
            f"投稿需要消耗 200 次元币，您当前只有 {remaining_coin:.1f} 次元币，余额不足！"
        )

    async with get_session() as session:
        caves = cave_models(details=details, user_id=user_id, img_base64=base64_images)
        session.add(caves)
        await session.commit()
        await session.refresh(caves)

        # 构建包含图片的消息序列
        img_seq: list[MessageSegment] = []

        # 投稿内容部分
        content_part = f"[投稿成功 #{caves.id}]\n{caves.details}"
        img_seq.append(MessageSegment.text(content=content_part))

        # 图片部分
        if caves.img_base64:
            img_seq.extend(
                [
                    MessageSegment.image(base64=img_base64)
                    for img_base64 in caves.img_base64
                ]
            )

        # 分割线和信息部分
        info_part = f"\n————————————\n投稿时间: {caves.time.strftime('%Y-%m-%d %H:%M:%S')}\n消耗次元币: 200 | 余额: {remaining_coin:.1f}"
        img_seq.append(MessageSegment.text(content=info_part))

        for i in SUPERUSER_list:
            await bot.send_private_message(
                user_id=int(i),
                message=Message(f"来自用户{event.get_user_id()}\n{result}"),
            )
        await cave_add.finish(message=Message(img_seq))


@cave_am_add.handle()
async def _(bot: Bot, event: MessageEvent):
    "匿名发布回声洞"
    has_image, clean_text, base64_images = await process_image_message(event)
    details = clean_text if has_image else str(event.get_message())
    details = details.replace("匿名投稿", "", 1).strip()
    result = await condition(event, details)
    if result[0] is False:  # 审核
        await cave_am_add.finish(result[1])

    # 扣除次元币
    user_id = event.data.sender_id
    success, remaining_coin = await subtract_coin(str(user_id), 400)
    if not success:
        await cave_am_add.finish(
            f"匿名投稿需要消耗 400 次元币，您当前只有 {remaining_coin:.1f} 次元币，余额不足！"
        )

    async with get_session() as session:
        caves = cave_models(
            details=details, user_id=user_id, anonymous=True, img_base64=base64_images
        )
        session.add(caves)
        await session.commit()
        await session.refresh(caves)  # 构建包含图片的消息序列
        img_seq: list[MessageSegment] = []

        # 投稿内容部分
        content_part = f"[匿名投稿成功 #{caves.id}]\n{caves.details}"
        img_seq.append(MessageSegment.text(content=content_part))

        # 图片部分
        if caves.img_base64:
            img_seq.extend(
                [
                    MessageSegment.image(base64=img_base64)
                    for img_base64 in caves.img_base64
                ]
            )

        # 分割线和信息部分
        info_part = f"\n————————————\n投稿时间: {caves.time.strftime('%Y-%m-%d %H:%M:%S')}\n匿名投稿会保存用户信息但其他用户无法看到作者\n消耗次元币: 400 | 余额: {remaining_coin:.1f}"
        img_seq.append(MessageSegment.text(content=info_part))

        for i in SUPERUSER_list:
            await bot.send_private_message(
                user_id=int(i),
                message=Message(f"来自用户{event.get_user_id()}\n{result}"),
            )
        await cave_am_add.finish(message=Message(img_seq))


@cave_del.handle()
async def _(bot: Bot, event: MessageEvent):
    Message_text = str(event.message)
    deletion_reasons = extract_deletion_reason(Message_text)
    key = deletion_reasons["序号"]
    # 如果有原因获取，没有为 none
    reason = deletion_reasons["原因"]
    try:
        key = int(key)
    except ValueError:
        await cave_del.finish("请输入正确的序号")

    async with get_session() as session:
        try:
            stmt = select(cave_models).where(cave_models.id == key)
            result = await session.execute(stmt)
            data = result.scalar_one()
        except Exception:
            await cave_del.finish("没有这个序号的投稿")

        # 判断是否是超级用户或者是投稿人
        if str(event.data.sender_id) in SUPERUSER_list:
            try:
                await bot.send_private_message(
                    user_id=data.user_id,
                    message=Message(
                        f"您的投稿 #{key} 已被管理员删除\n内容: {data.details}\n删除原因: {reason}"
                    ),
                )
            except Exception:
                logger.exception(
                    f"回声洞删除投稿私聊通知失败，投稿人 id：{data.user_id}"
                )
                await cave_del.send("删除失败，私聊通知失败")
        elif event.data.sender_id == data.user_id:
            await session.delete(data)
            await session.commit()
            img_seq: list[MessageSegment] = []

            # 投稿内容部分
            content_part = f"[删除成功] 编号 {key} 的投稿已删除\n内容: {data.details}"
            img_seq.append(MessageSegment.text(content=content_part))

            # 图片部分
            if data.img_base64:
                img_seq.extend(
                    [
                        MessageSegment.image(base64=img_base64)
                        for img_base64 in data.img_base64
                    ]
                )

            await cave_del.finish(message=Message(img_seq))
        else:
            await cave_del.finish("您没有权限删除此投稿")

        await session.delete(data)
        await session.commit()

        img_seq: list[MessageSegment] = []

        # 投稿内容部分
        content_part = f"[删除成功] 编号 {key} 的投稿已删除\n内容: {data.details}"
        img_seq.append(MessageSegment.text(content=content_part))

        # 图片部分
        if data.img_base64:
            img_seq.extend(
                [
                    MessageSegment.image(base64=img_base64)
                    for img_base64 in data.img_base64
                ]
            )

        # 分割线和删除原因部分
        reason_part = f"\n————————————\n删除原因: {reason}"
        img_seq.append(MessageSegment.text(content=reason_part))

        await cave_main.finish(message=Message(img_seq))


@cave_main.handle()
async def _(args: Message = CommandArg()):
    key = str(args).strip()

    async with get_session() as session:
        if not key:
            stmt = select(cave_models)
            result = await session.execute(stmt)
            all_caves = result.scalars().all()

            if not all_caves:
                await cave_main.finish("回声洞暂时还没有投稿呢")

            random_cave = random.choice(all_caves)
            displayname = (
                "匿名用户" if random_cave.anonymous else f"用户{random_cave.user_id}"
            )

            img_seq: list[MessageSegment] = []

            # 投稿内容部分
            content_part = f"[回声洞 #{random_cave.id}]\n{random_cave.details}"
            img_seq.append(MessageSegment.text(content=content_part))

            # 图片部分
            if random_cave.img_base64:
                img_seq.extend(
                    [
                        MessageSegment.image(base64=img_base64)
                        for img_base64 in random_cave.img_base64
                    ]
                )

            # 分割线和信息部分
            info_part = f"\n————————————\n投稿人：{displayname}\n时间：{random_cave.time.strftime('%Y-%m-%d %H:%M:%S')}\n\n私聊机器人可以投稿：\n投稿 [内容] | 匿名投稿 [内容]"
            img_seq.append(MessageSegment.text(content=info_part))

            await cave_main.finish(message=Message(img_seq))
        else:
            # 验证输入是否为有效的数字
            try:
                cave_id = int(key)
            except ValueError:
                await cave_main.finish("请输入有效的数字编号")

            stmt = select(cave_models).where(cave_models.id == cave_id)
            result = await session.execute(stmt)
            cave = result.scalar_one_or_none()

            if cave is None:
                await cave_main.finish("没有这个序号的投稿")

            # 判断是否是匿名
            displayname = "匿名用户" if cave.anonymous else f"用户{cave.user_id}"

            img_seq: list[MessageSegment] = []

            # 投稿内容部分
            content_part = f"[回声洞 #{cave.id}]\n{cave.details}"
            img_seq.append(MessageSegment.text(content=content_part))

            # 图片部分
            if cave.img_base64:
                img_seq.extend(
                    [
                        MessageSegment.image(base64=img_base64)
                        for img_base64 in cave.img_base64
                    ]
                )

            # 分割线和信息部分
            info_part = f"\n————————————\n投稿人: {displayname}\n时间: {cave.time.strftime('%Y-%m-%d %H:%M:%S')}\n\n私聊机器人可以投稿:\n投稿 [内容] | 匿名投稿 [内容]"
            img_seq.append(MessageSegment.text(content=info_part))

            await cave_main.finish(message=Message(img_seq))


@cave_history.handle()
async def _(bot: Bot, event: MessageEvent):
    # 查询 userid 写所有数据
    async with get_session() as session:
        stmt = select(cave_models).where(cave_models.user_id == event.data.sender_id)
        result = await session.execute(stmt)
        all_caves = result.scalars().all()

        if not all_caves:
            await cave_history.finish("您还没有任何投稿记录")

        # 构造转发消息
        messages: list[list[MessageSegment]] = []
        messages.append([MessageSegment.text("您的回声洞投稿记录:")])

        # 添加每个投稿记录
        for i in all_caves:
            # 为每个投稿构建消息段列表
            msg_segments: list[MessageSegment] = []

            # 投稿内容部分
            content_part = f"[编号 #{i.id}]\n{i.details}"
            msg_segments.append(MessageSegment.text(content=content_part))

            # 图片部分
            if i.img_base64:
                msg_segments.extend(
                    [
                        MessageSegment.image(base64=img_base64)
                        for img_base64 in i.img_base64
                    ]
                )

            # 分割线和信息部分
            info_part = (
                f"\n————————————\n投稿时间: {i.time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            msg_segments.append(MessageSegment.text(content=info_part))

            messages.append(msg_segments)

        forward_msgs = [
            OutgoingForwardedMessage(
                name=Bot_NICKNAME,
                user_id=int(bot.self_id),
                segments=msg_segments,
            )
            for msg_segments in messages
        ]

        await cave_history.finish(MessageSegment.forward(forward_msgs))


def extract_deletion_reason(text):
    """
    从文本中提取删除原因，处理“删除1”或“删除 1 原因1”等格式。

    Args:
        text (str): 包含删除原因的文本。

    Returns:
        dict: 包含删除原因的字典，包含序号和原因。

    Example:
        >>> text = "删除1 原因1"
        >>> extract_deletion_reason(text)
        {'序号': 1, '原因': '原因1'}
    """
    # 移除 "删除" 关键字以及多余的空格
    cleaned_text = text.replace("删除", "", 1).strip()

    # 分离序号和原因
    num = ""
    reason = ""

    # 通过第一个非数字字符来划分序号和原因
    for idx, char in enumerate(cleaned_text):
        if char.isdigit():
            num += char
        else:
            # 当遇到第一个非数字字符时，余下部分全是原因
            reason = cleaned_text[idx:].strip()
            break

    # 若没有原因，则设为默认值 "作者删除"
    if not reason:
        reason = "作者删除"

    return {"序号": int(num), "原因": reason}
