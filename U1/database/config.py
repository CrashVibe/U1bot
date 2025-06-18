from pydantic import BaseModel


class Config(BaseModel):
    sqlalchemy_database_url: str | None = None
