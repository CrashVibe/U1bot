from typing import Any, Generic, TypeVar

from sqlalchemy import delete as sa_delete, select, update as sa_update

from nonebot import require

require("nonebot_plugin_orm")

from nonebot_plugin_orm import Model as NBModel, get_scoped_session


T = TypeVar("T", bound="BaseModel")


class Query(Generic[T]):
    def __init__(self, model: type[T], filters: dict[str, Any]):
        self._model: type[T] = model
        self._filters = filters

    def _where(self):
        return select(self._model).filter_by(**self._filters)

    async def all(self) -> list[T]:
        session = get_scoped_session()
        result = await session.execute(self._where())
        return list(result.scalars().all())

    async def delete(self) -> None:
        session = get_scoped_session()
        await session.execute(sa_delete(self._model).filter_by(**self._filters))
        await session.commit()

    async def update(self, **values: Any) -> None:
        session = get_scoped_session()
        await session.execute(
            sa_update(self._model).filter_by(**self._filters).values(**values)
        )
        await session.commit()


class BaseModel(NBModel):
    @classmethod
    def filter(cls: type[T], **kwargs: Any) -> Query[T]:  # type: ignore[override]
        return Query(cls, kwargs)

    @classmethod
    async def all(cls: type[T]) -> list[T]:  # type: ignore[override]
        session = get_scoped_session()
        result = await session.execute(select(cls))
        return list(result.scalars().all())

    @classmethod
    async def get(cls: type[T], **kwargs: Any) -> T:  # type: ignore[override]
        session = get_scoped_session()
        result = await session.execute(select(cls).filter_by(**kwargs))
        obj = result.scalars().first()
        if obj is None:
            raise ValueError("object not found")
        return obj

    @classmethod
    async def get_or_none(cls: type[T], **kwargs: Any) -> T | None:
        session = get_scoped_session()
        result = await session.execute(select(cls).filter_by(**kwargs))
        return result.scalars().first()

    @classmethod
    async def create(cls: type[T], **kwargs: Any) -> T:
        session = get_scoped_session()
        obj = cls(**kwargs)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    @classmethod
    async def get_or_create(cls: type[T], **kwargs: Any) -> tuple[T, bool]:
        obj = await cls.get_or_none(**kwargs)
        if obj:
            return obj, False
        return await cls.create(**kwargs), True

    async def save(self: T) -> None:  # type: ignore[override]
        session = get_scoped_session()
        session.add(self)
        await session.commit()

    async def delete(self: T) -> None:  # type: ignore[override]
        session = get_scoped_session()
        await session.delete(self)
        await session.commit()


# Export BaseModel as Model for backward compatibility
Model = BaseModel


async def connect() -> None:
    """Initialize database (handled automatically by plugin)."""
    return None


async def disconnect() -> None:
    """Close scoped session."""
    try:
        get_scoped_session().remove()  # pyright: ignore[reportUnusedCoroutine]
    except Exception:
        pass


def add_model(model: str, db_name: str | None = None, db_url: str | None = None) -> None:
    """Compatibility placeholder for old API."""
    return None

__all__ = ["Model", "connect", "disconnect", "add_model", "get_scoped_session"]
