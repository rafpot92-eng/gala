from contextlib import contextmanager

import psycopg

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str

    jwt_secret: str

    frontend_url: str = "http://localhost:3000"

    jwt_expire_minutes: int = 480

    class Config:
        env_file = ".env"


settings = Settings()


@contextmanager
def get_connection():
    with psycopg.connect(settings.database_url) as conn:
        yield conn