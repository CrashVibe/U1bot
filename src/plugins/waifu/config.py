from pydantic import BaseModel


class Config(BaseModel, extra="ignore"):
    waifu_cd_bye: int = 3600
    waifu_save: bool = True
    waifu_reset: bool = True
    waifu_he: int = 40
    waifu_be: int = 20
    waifu_ntr: int = 50
    yinpa_be: int = 0
    yinpa_cp: int = 80
    waifu_last_sent_time_filter: int = 2592000
    yinpa_cd: int = 300
    yinpa_he: int = 60
    free_divorce_reset_hour: int = 4


settings = Config()
