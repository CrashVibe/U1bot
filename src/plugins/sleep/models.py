from datetime import datetime

from tortoise import Model, fields
from tortoise.fields import Field

from U1.database import add_model

add_model(__name__)


class SleepGroupModel(Model):
    group_id = fields.CharField(pk=True, max_length=32)

    # 每日早晚安
    morning_count = fields.IntField(default=0)
    night_count = fields.IntField(default=0)

    class Meta:
        table = "sleep_group"


class SleepUserModel(Model):
    user_id = fields.CharField(pk=True, max_length=32)

    # 每日早晚安
    night_time: Field[datetime] | None = fields.DatetimeField(null=True, default=None)
    morning_time: Field[datetime] | None = fields.DatetimeField(null=True, default=None)

    # 每周早晚安
    weekly_morning_cout = fields.IntField(default=0)  # 早安次数
    weekly_night_cout = fields.IntField(default=0)  # 晚安次数
    weekly_sleep_time = fields.IntField(default=0)  # 睡觉时间
    weekly_earliest_morning_time: Field[datetime] | None = fields.DatetimeField(
        null=True, default=None
    )  # 最早起床时间
    weekly_latest_night_time: Field[datetime] | None = fields.DatetimeField(
        null=True, default=None
    )  # 最晚睡觉时间

    # 这周迁移到上周
    lastweek_morning_cout = fields.IntField(default=0)
    lastweek_night_cout = fields.IntField(default=0)
    lastweek_sleep_time = fields.IntField(default=0)
    lastweek_earliest_morning_time: Field[datetime] | None = fields.DatetimeField(
        null=True, default=None
    )
    lastweek_latest_night_time: Field[datetime] | None = fields.DatetimeField(
        null=True, default=None
    )

    # 总数
    morning_count = fields.IntField(default=0)
    night_count = fields.IntField(default=0)
    total_sleep_time = fields.IntField(default=0)

    class Meta:
        table = "sleep_user"
