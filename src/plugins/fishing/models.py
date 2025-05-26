from tortoise import fields
from tortoise.models import Model

from U1.database import add_model

add_model(__name__)


class FishingRecord(Model):
    id = fields.IntField(pk=True)
    user_id = fields.CharField(max_length=32)
    time = fields.IntField()
    frequency = fields.IntField()
    fishes = fields.TextField()
    coin = fields.FloatField(default=0)
    count_coin = fields.FloatField(default=0)

    class Meta:
        table = "fishing_fishingrecord"


class FishingSwitch(Model):
    group_id = fields.IntField(pk=True)
    switch = fields.BooleanField(default=True)

    class Meta:
        table = "fishing_fishingswitch"
