# 导入插件方法
from nonebot_plugin_tortoise_orm import add_model
from tortoise import fields
from tortoise.models import Model

add_model(__name__)


class MemberData(Model):
    user_id = fields.BigIntField(pk=True)
    luckid = fields.IntField(default=0)
    time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "today_yunshi_memberdata"
