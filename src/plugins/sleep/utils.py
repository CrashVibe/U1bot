from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .config import settings

if TYPE_CHECKING:
    from datetime import time as _Time

# 缓存的提示语列表，避免重复列表创建
MORNING_PROMPTS: tuple[str, ...] = (
    "元气满满的一天开始啦！ (/▽＼)",
    "迎接美好的一天吧！ (￣▽￣)~*",
    "今天也要干劲满满哦~ (๑•̀ㅂ•́)و✧",
    "今天也要加油哦！ (ง •_•)ง",
)

NIGHT_PROMPTS: tuple[str, ...] = (
    "很累了罢~(。-ω-)zzz",
    "祝你有个好梦～(￣o￣) . z Z",
    "晚安(∪｡∪)｡｡｡zzz",
    "おやすみなさい～(´-ω-)`~*",
    "睡个好觉哦(˘ω˘)ｽﾞﾔｧ…",
)

# 为了向后兼容，保留列表形式的引用
morning_prompt = list(MORNING_PROMPTS)
night_prompt = list(NIGHT_PROMPTS)

# 缓存常用的时间常量
_SECONDS_PER_DAY = 86400
_SECONDS_PER_HOUR = 3600
_SECONDS_PER_MINUTE = 60


def datetime2timedelta(dt: datetime) -> timedelta:
    """将datetime转换为当日的timedelta，优化版本"""
    # 使用更高效的方式计算当日时间差
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt - midnight


def total_seconds2tuple_time(secs: int) -> tuple[int, int, int, int]:
    """将总秒数转换为天数、小时、分钟、秒数的元组 - 优化版本"""
    # 使用位运算和常量提高性能
    days, remainder = divmod(secs, _SECONDS_PER_DAY)
    hours, remainder = divmod(remainder, _SECONDS_PER_HOUR)
    minutes, seconds = divmod(remainder, _SECONDS_PER_MINUTE)
    return days, hours, minutes, seconds


def isTimeInMorningRange(early_time: int, late_time: int, now_time: datetime) -> bool:
    """判断早安时间是否在范围内 - 优化版本"""
    current_hour_delta = datetime2timedelta(now_time)
    early_delta = timedelta(hours=early_time)
    late_delta = timedelta(hours=late_time)
    return early_delta < current_hour_delta < late_delta


def isTimeInNightRange(early_time: int, late_time: int, now_time: datetime) -> bool:
    """判断晚安时间是否在范围内 - 优化版本，支持跨夜"""
    current_hour_delta = datetime2timedelta(now_time)
    early_delta = timedelta(hours=early_time)
    late_delta = timedelta(hours=late_time)

    # 夜间时间跨越零点的情况
    return current_hour_delta > early_delta or current_hour_delta < late_delta


def get_adjusted_minutes(time_obj: "_Time") -> tuple[int, bool]:
    """获取调整后的分钟数 - 优化版本"""
    total_minutes = time_obj.hour * 60 + time_obj.minute
    late_time_hour = settings.night_night_intime_late_time
    early_time_hour = settings.night_night_intime_early_time

    # 凌晨时段（0点-late_time点）
    if 0 <= time_obj.hour < late_time_hour:
        return total_minutes + 1440, True  # 加24小时的分钟数
    # 夜晚时段（early_time点-23点）
    elif early_time_hour <= time_obj.hour <= 23:
        return total_minutes, False

    raise ValueError(f"时间 {time_obj.hour}:{time_obj.minute} 不在有效范围内")


def check_morning_time_in_range(morning_time: datetime, now_time: datetime) -> bool:
    """检查现在时间是否在早安范围内 - 优化版本"""
    early = settings.morning_morning_intime_early_time
    late = settings.morning_morning_intime_late_time

    # 检查小时范围和日期是否相同
    return early <= now_time.hour <= late and morning_time.date() == now_time.date()


def format_sleep_duration(seconds: int) -> str:
    """格式化睡眠时长显示 - 新增优化函数"""
    if seconds <= 0:
        return "0秒"

    days, hours, minutes, secs = total_seconds2tuple_time(seconds)

    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if secs > 0 or not parts:  # 如果没有其他部分，至少显示秒数
        parts.append(f"{secs}秒")

    return "".join(parts)
