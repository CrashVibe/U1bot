from pydantic import BaseModel


class Config(BaseModel, extra="ignore"):
    morning_morning_intime_enable: bool = True
    morning_morning_intime_early_time: int = 6
    morning_morning_intime_late_time: int = 12

    morning_mult_get_up_enable: bool = False
    morning_mult_get_up_interval: int = 6

    morning_super_get_up_enable: bool = False
    morning_super_get_up_interval: int = 1

    night_night_intime_enable: bool = True
    night_night_intime_early_time: int = 21
    night_night_intime_late_time: int = 6

    night_good_sleep_enable: bool = True
    night_good_sleep_interval: int = 6

    night_deep_sleep_enable: bool = False
    night_deep_sleep_interval: int = 3


settings = Config()
