import json
import math
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import httpx
import jinja2
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_htmlrender import html_to_pic
from nonebot_plugin_localstore import get_cache_dir

from .config import ddcheck_config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 "
        "Safari/537.36 Edg/114.0.1823.67"
    ),
    "Referer": "https://www.bilibili.com/",
}

data_path = get_cache_dir("nonebot_plugin_ddcheck")
vtb_list_path = data_path / "vtb_list.json"

dir_path = Path(__file__).parent
template_path = dir_path / "template"
env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(template_path), enable_async=True
)

raw_cookie = ddcheck_config.bilibili_cookie
cookie = SimpleCookie()
cookie.load(raw_cookie)
cookies = {key: value.value for key, value in cookie.items()}

homepage_cookies: dict[str, str] = {}


async def update_vtb_list():
    """更新VTB列表"""
    vtb_list = []
    urls = [
        "https://api.vtbs.moe/v1/short",
        "https://cfapi.vtbs.moe/v1/short",
        "https://hkapi.vtbs.moe/v1/short",
        "https://kr.vtbs.moe/v1/short",
    ]
    async with httpx.AsyncClient() as client:
        for url in urls:
            try:
                resp = await client.get(url, timeout=20)
                result = resp.json()
                if not result:
                    continue
                for info in result:
                    if info.get("uid", None) and info.get("uname", None):
                        vtb_list.append(
                            {"mid": int(info["uid"]), "uname": info["uname"]}
                        )
                    if info.get("mid", None) and info.get("uname", None):
                        vtb_list.append(info)
                break
            except httpx.TimeoutException:
                logger.warning(f"Get {url} timeout")
            except Exception:
                logger.exception(f"Error when getting {url}, ignore")
    dump_vtb_list(vtb_list)


scheduler.add_job(
    update_vtb_list,
    "cron",
    hour=3,
    id="update_vtb_list",
)


def load_vtb_list() -> list[dict]:
    """加载VTB列表"""
    if vtb_list_path.exists():
        with vtb_list_path.open("r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.decoder.JSONDecodeError:
                logger.warning("vtb列表解析错误，将重新获取")
                vtb_list_path.unlink()
    return []


def dump_vtb_list(vtb_list: list[dict]):
    """保存VTB列表"""
    data_path.mkdir(parents=True, exist_ok=True)
    json.dump(
        vtb_list,
        vtb_list_path.open("w", encoding="utf-8"),
        indent=4,
        separators=(",", ": "),
        ensure_ascii=False,
    )


async def get_vtb_list() -> list[dict]:
    """获取VTB列表，若本地无则自动更新"""
    vtb_list = load_vtb_list()
    if not vtb_list:
        await update_vtb_list()
    return load_vtb_list()


async def get_homepage_cookies(client: httpx.AsyncClient) -> dict[str, str]:
    """获取B站首页Cookies"""
    if not homepage_cookies:
        headers = {"User-Agent": HEADERS["User-Agent"]}
        resp = await client.get(
            "https://data.bilibili.com/v/", headers=headers, follow_redirects=True
        )
        homepage_cookies.update(resp.cookies)
    return homepage_cookies


async def get_uid_by_name(name: str) -> int | None:
    """通过用户名获取UID"""
    url = "https://api.bilibili.com/x/web-interface/wbi/search/type"
    params = {"search_type": "bili_user", "keyword": name}
    async with httpx.AsyncClient(timeout=10) as client:
        cookies.update(await get_homepage_cookies(client))
        resp = await client.get(url, params=params, headers=HEADERS, cookies=cookies)
        cookies.update(resp.cookies)
        result = resp.json()
        logger.info(f"get_uid_by_name: {result}")
        for user in result["data"]["result"]:
            if user["uname"] == name:
                return user["mid"]


async def get_medal_list(uid: int) -> list[dict]:
    """获取用户勋章列表"""
    url = "https://api.live.bilibili.com/xlive/web-ucenter/user/MedalWall"
    params = {"target_id": uid}
    async with httpx.AsyncClient(timeout=10) as client:
        cookies.update(await get_homepage_cookies(client))
        resp = await client.get(url, params=params, headers=HEADERS, cookies=cookies)
        cookies.update(resp.cookies)
        result = resp.json()
        return result["data"]["list"]


API_CONFIGS = [
    {
        "name": "app.biliapi.net",
        "url": "https://app.biliapi.net/x/v2/relation/followings",
        "max_pages": 5,
    },
    {
        "name": "biligame",
        "url": "https://line3-h5-mobile-api.biligame.com/game/center/h5/user/relationship/following_list",
        "max_pages": 20,
    },
]

PAGE_SIZE = 50


async def get_api_data(url: str, params: dict) -> dict:
    """通用API请求函数"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params, headers=HEADERS)
        return resp.json()


async def fetch_all_followings(uid: int, api_config: dict) -> list[int]:
    """使用指定API获取完整关注列表"""
    followings = []
    page = 1
    while page <= api_config["max_pages"]:
        try:
            params = {"vmid": uid, "pn": page, "ps": PAGE_SIZE}
            result = await get_api_data(api_config["url"], params)
            if result["code"] != 0:
                if page == 1:
                    raise Exception(f"API错误: {result.get('message', '未知错误')}")
                break
            page_list = result.get("data", {}).get("list", [])
            if not page_list:
                break
            page_followings = [int(user["mid"]) for user in page_list]
            followings.extend(page_followings)
            logger.info(f"第 {page} 页获取 {len(page_followings)} 个关注")
            if len(page_followings) < PAGE_SIZE:
                break
            page += 1
        except Exception as e:
            if page == 1:
                raise e
            logger.warning(f"第 {page} 页获取失败: {e}")
            break
    return followings


async def get_user_basic_info(uid: int) -> dict:
    """获取用户基本信息"""
    default_info = {"name": f"用户{uid}", "face": "", "follower": 0, "following": 0}
    try:
        result = await get_api_data(
            "https://api.bilibili.com/x/web-interface/card", {"mid": uid}
        )
        if result["code"] == 0:
            card = result["data"]["card"]
            return {
                "name": card.get("name", default_info["name"]),
                "face": card.get("face", ""),
                "follower": result["data"].get("follower", 0),
                "following": card.get("attention", 0),
            }
    except Exception as e:
        logger.warning(f"获取用户基本信息失败: {e}")
    try:
        result = await get_api_data(
            "https://app.biliapi.net/x/v2/relation/followings",
            {"vmid": uid, "pn": 1, "ps": 1},
        )
        if result["code"] == 0:
            default_info["following"] = result.get("data", {}).get("total", 0)
    except Exception:
        pass
    return default_info


async def get_user_followings(uid: int) -> list[int]:
    """获取用户关注列表"""
    for api_config in API_CONFIGS:
        try:
            logger.info(f"尝试使用 {api_config['name']} API")
            followings = await fetch_all_followings(uid, api_config)
            if followings:
                logger.info(
                    f"{api_config['name']} API 成功获取 {len(followings)} 个关注"
                )
                return followings
        except Exception as e:
            logger.warning(f"{api_config['name']} API 失败: {e}")
    logger.error(f"所有API都失败，无法获取用户 {uid} 的关注列表")
    return []


async def get_user_info(uid: int) -> dict:
    """获取用户完整信息，包含基本信息和关注列表"""
    try:
        import asyncio

        basic_info_task = asyncio.create_task(get_user_basic_info(uid))
        followings_task = asyncio.create_task(get_user_followings(uid))
        basic_info, followings = await asyncio.gather(
            basic_info_task, followings_task, return_exceptions=True
        )
        if isinstance(basic_info, Exception):
            logger.error(f"获取用户 {uid} 基本信息失败: {basic_info}")
            basic_info = {
                "name": f"用户{uid}",
                "face": "",
                "follower": 0,
                "following": 0,
            }
        if isinstance(followings, Exception):
            logger.error(f"获取用户 {uid} 关注列表失败: {followings}")
            followings = []
    except Exception as e:
        logger.error(f"获取用户 {uid} 信息时发生异常: {e}")
        basic_info = {"name": f"用户{uid}", "face": "", "follower": 0, "following": 0}
        followings = []
    if not isinstance(basic_info, dict):
        basic_info = {"name": f"用户{uid}", "face": "", "follower": 0, "following": 0}
    if not isinstance(followings, list):
        followings = []
    return {
        "mid": str(uid),
        "name": basic_info.get("name", f"用户{uid}"),
        "face": basic_info.get("face", ""),
        "fans": basic_info.get("follower", 0),
        "attention": basic_info.get("following", len(followings)),
        "attentions": followings,
    }


def format_color(color: int) -> str:
    """格式化颜色为十六进制字符串"""
    return f"#{color:06X}"


def format_vtb_info(info: dict, medal_dict: dict) -> dict:
    """格式化VTB信息"""
    name = info["uname"]
    uid = info["mid"]
    medal = {}
    if name in medal_dict:
        medal_info = medal_dict[name]["medal_info"]
        medal = {
            "name": medal_info["medal_name"],
            "level": medal_info["level"],
            "color_border": format_color(medal_info["medal_color_border"]),
            "color_start": format_color(medal_info["medal_color_start"]),
            "color_end": format_color(medal_info["medal_color_end"]),
        }
    return {"name": name, "uid": uid, "medal": medal}


async def render_ddcheck_image(
    user_info: dict[str, Any], vtb_list: list[dict], medal_list: list[dict]
) -> bytes:
    """渲染成分检查图片"""
    attentions = user_info.get("attentions", [])
    follows_num = int(user_info["attention"])
    attention_set = set(attentions)
    vtb_dict = {info["mid"]: info for info in vtb_list}
    medal_dict = {medal["target_name"]: medal for medal in medal_list}
    vtbs = [
        format_vtb_info(info, medal_dict)
        for uid, info in vtb_dict.items()
        if uid in attention_set
    ]
    vtbs_num = len(vtbs)
    percent = (vtbs_num / follows_num * 100) if follows_num else 0
    num_per_col = math.ceil(vtbs_num / math.ceil(vtbs_num / 100)) if vtbs_num else 1
    result = {
        "name": user_info["name"],
        "uid": user_info["mid"],
        "face": user_info["face"],
        "fans": user_info["fans"],
        "follows": follows_num,
        "percent": f"{percent:.2f}% ({vtbs_num}/{follows_num})",
        "vtbs": vtbs,
        "num_per_col": num_per_col,
    }
    template = env.get_template("info.html")
    content = await template.render_async(info=result)
    return await html_to_pic(content, wait=0, viewport={"width": 100, "height": 100})
