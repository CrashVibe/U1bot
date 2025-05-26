from pydantic import BaseModel


class Config(BaseModel):
    tortoise_orm_db_url: str | None = None
