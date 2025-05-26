# 导入插件方法
from tortoise import fields
from tortoise.models import Model

from U1.database import add_model

add_model(__name__)


class MemberData(Model):
    user_id = fields.BigIntField(pk=True)
    luckid = fields.IntField(default=0)
    time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "today_yunshi_memberdata"
