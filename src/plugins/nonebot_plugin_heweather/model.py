from enum import IntEnum

from pydantic import BaseModel, ConfigDict


class Now(BaseModel):
    model_config = ConfigDict(extra="allow")

    obsTime: str
    temp: str
    icon: str
    text: str
    windScale: str
    windDir: str
    humidity: str
    precip: str
    vis: str


class NowApi(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    now: Now


class Daily(BaseModel):
    model_config = ConfigDict(extra="allow")

    fxDate: str
    week: None | str = None
    date: None | str = None
    tempMax: str
    tempMin: str
    textDay: str
    textNight: str
    iconDay: str
    iconNight: str


class DailyApi(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    daily: list[Daily]


class Air(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: str
    aqi: str
    pm2p5: str
    pm10: str
    o3: str
    co: str
    no2: str
    so2: str
    tag_color: None | str = None


class AirApi(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    now: None | Air = None


class Warning(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    type: str
    pubTime: str
    text: str


class WarningApi(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    warning: None | list[Warning] = None


class Hourly(BaseModel):
    model_config = ConfigDict(extra="allow")

    fxTime: str
    hour: None | str = None
    temp: str
    icon: str
    text: str
    temp_percent: None | str = None


class HourlyApi(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str
    hourly: list[Hourly]


class HourlyType(IntEnum):
    current_12h = 1
    current_24h = 2
