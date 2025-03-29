from nonebot_plugin_tortoise_orm import add_model
from tortoise import fields
from tortoise.models import Model

add_model(__name__)


class Channel(Model):
    id = fields.CharField(max_length=255, pk=True)
    platform = fields.CharField(max_length=255)
    flag = fields.BigIntField(unsigned=True, default=0, null=True)
    assignee = fields.CharField(max_length=255, null=True)
    guildId = fields.CharField(max_length=255, null=True)
    locales = fields.TextField(null=True, default=None)
    permissions = fields.TextField(null=True, default=None)
    createdAt = fields.DatetimeField(null=True, default=None)

    class Meta:
        unique_together = ("platform", "flag")
