from nonebot_plugin_tortoise_orm import add_model
from tortoise import fields
from tortoise.models import Model

add_model(__name__)


class BaseGroupModel(Model):
    group_id = fields.BigIntField(pk=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        abstract = True


class WaifuProtect(BaseGroupModel):
    user_ids = fields.JSONField(default=[])

    class Meta:
        table = "waifu_protect"


class WaifuCP(BaseGroupModel):
    affect = fields.JSONField(default={})

    class Meta:
        table = "waifu_cp"


class PWaifu(BaseGroupModel):
    waifu_list = fields.JSONField(default=[])

    class Meta:
        table = "waifu"


class WaifuLock(BaseGroupModel):
    lock = fields.JSONField(default={})

    class Meta:
        table = "waifu_lock"


class YinpaRecord(Model):
    user_id = fields.BigIntField(pk=True)
    active_count = fields.IntField(default=0)
    passive_count = fields.IntField(default=0)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        abstract = True


class YinpaActive(YinpaRecord):
    class Meta:
        table = "yinpa_active"


class YinpaPassive(YinpaRecord):
    class Meta:
        table = "yinpa_passive"
