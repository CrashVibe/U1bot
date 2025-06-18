from nonebot import require

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model, get_scoped_session


async def connect() -> None:
    """Initialize database (handled automatically by plugin)."""
    return None


async def disconnect() -> None:
    """Close scoped session."""
    try:
        get_scoped_session().remove()
    except Exception:
        pass


def add_model(model: str, db_name: str | None = None, db_url: str | None = None) -> None:
    """Compatibility placeholder for old API."""
    return None

__all__ = ["Model", "connect", "disconnect", "add_model", "get_scoped_session"]
