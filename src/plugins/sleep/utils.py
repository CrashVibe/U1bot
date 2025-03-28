from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .config import settings

if TYPE_CHECKING:
    from datetime import _Time

# morning_prompt: list[str] = [
#     "早安，元气满满！",
#     "起床啦，迎接美好的一天！",
#     "早安，今天干劲满满~",
# ]

# night_prompt: list[str] = ["很累了罢~", "祝你有个好梦~", "晚安~", "おやすみなさい~"]


morning_prompt: list[str] = [
    "元气满满的一天开始啦！ (/▽＼)",
    "迎接美好的一天吧！ (￣▽￣)~*",
    "今天也要干劲满满哦~ (๑•̀ㅂ•́)و✧",
    "今天也要加油哦！ (ง •_•)ง",
]

night_prompt: list[str] = [
    "很累了罢~(。-ω-)zzz",
    "祝你有个好梦～(￣o￣) . z Z",
    "晚安(∪｡∪)｡｡｡zzz",
    "おやすみなさい～(´-ω-)`~*",
    "睡个好觉哦(˘ω˘)ｽﾔｧ…",
]


def datetime2timedelta(_datetime: datetime) -> timedelta:
    return _datetime - datetime(
        _datetime.year, _datetime.month, _datetime.day, 0, 0, 0, tzinfo=_datetime.tzinfo
    )


def isTimeInMorningRange(early_time: int, late_time: int, now_time: datetime) -> bool:
    """
    判断早安时间是否在范围内
    - early_time: 较早的开始时间
    - late_time: 较晚的结束时间
    """
    return (
        timedelta(hours=early_time)
        < datetime2timedelta(now_time)
        < timedelta(hours=late_time)
    )


def total_seconds2tuple_time(secs: int) -> tuple[int, int, int, int]:
    days, secs = divmod(secs, 86400)
    hours, secs = divmod(secs, 3600)
    minutes, seconds = divmod(secs, 60)
    return days, hours, minutes, seconds


def isTimeInNightRange(early_time: int, late_time: int, now_time: datetime) -> bool:
    """
    判断晚安时间是否在范围内，注意次日判断
    - early_time: 较早的开始时间
    - late_time: 较晚的结束时间
    """
    return datetime2timedelta(now_time) > timedelta(
        hours=early_time
    ) or datetime2timedelta(now_time) < timedelta(hours=late_time)


def get_adjusted_minutes(time_obj: "_Time") -> tuple[int, bool]:
    """获取调整后的分钟数"""
    hour = time_obj.hour
    minutes = time_obj.minute
    total = hour * 60 + minutes
    if 0 <= hour < settings.night_night_intime_late_time:  # 凌晨时段（0点-x点）
        return total + 1440, True
    elif 22 <= hour <= 23:
        return total, False
    raise ValueError("时间不在范围内")
