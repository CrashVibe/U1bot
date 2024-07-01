from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    fish_rotten: list = [
        "喝醉的鱼",
        "摆烂的鱼",
        "腐烂的螃蟹",
        "腐烂的乌贼",
        "腐烂的龙虾",
        "腐烂的海星",
        "腐烂的空心鱼",
        "腐烂的触手",
        "腐烂的海参",
    ]

    fish_moldy: list = [
        "上过大学的鱼",
        "大专学历的鱼",
        "社恐鱼",
        "Code 鱼",
        "404 鱼",
        "贴图错误鱼" "发霉的鲤鱼",
        "发霉的鳗鱼",
        "发霉的鲭鱼",
        "发霉的鲑鱼",
    ]

    fish_common: list = [
        "尚方宝剑",
        "丁真鱼",
        "抑郁鱼",
        "鲤鱼",
        "水母",
        "虾",
        "鲭鱼",
        "龙虾",
        "鲑鱼",
        "鱿鱼",
        "海星",
        "鳗鱼",
        "海参",
        "鲷鱼",
        "鲢鱼",
        "多宝鱼" "龙利鱼" "墨鱼",
    ]

    fish_golden: list = [
        "林北卖的鱼",
        "林北的四文鱼",
        "小杂鱼~♡",
        "痛苦的鲑鱼",
        "金钓鱼竿",
        "金鲤鱼",
        "金螃蟹",
        "金鳗鱼",
        "金蛙",
        "金水母",
        "金龙虾",
        "金鲭鱼",
        "金河豚",
        "金岩鱼",
        "金乌贼",
        "金海星",
        "金空心鱼",
    ]

    fish_void: list = [
        "心海",
        "派蒙",
        "纯水精灵",
        "虚空鳗鱼",
        "烤激光鱼",
        "鲑鱼大帝",
        "虚空珍珠",
        "虚空鱼",
        "虚空海星",
    ]

    fish_hidden_fire: list = [
        "河",
        "Mr.ling",
        "闪耀珍珠",
        "隐火水母",
        "隐火龙虾",
        "隐火河豚",
        "隐火岩鱼",
        "隐火鲑鱼",
    ]

    fishing_limit: int = 30  # 钓鱼间隔 (s)
    fishing_coin_name: str = "次元币"  # 货币名称


config = get_plugin_config(Config)
