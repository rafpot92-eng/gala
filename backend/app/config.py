from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings


def _pg_env(data, name):

    for key in (name, name.lower(), name.upper()):

        if key in data and data[key]:

            return data[key]

    return None


class Settings(BaseSettings):

    database_url: str

    jwt_secret: str

    jwt_expire_minutes: int = 480

    frontend_url: str = "http://localhost:3000"

    backend_url: str = "http://localhost:8000"

    databricks_workspace_url: str

    databricks_client_id: str

    databricks_client_secret: str

    cookie_secure: bool = False

    cookie_samesite: str = "lax"

    cookie_domain: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _compose_database_url(cls, data):

        if isinstance(data, dict) and not data.get("database_url"):

            pg = {
                key: _pg_env(data, key)
                for key in (
                    "PGHOST",
                    "PGDATABASE",
                    "PGUSER",
                    "PGPASSWORD",
                    "PGPORT",
                    "PGSSLMODE",
                )
            }

            if pg["PGHOST"] and pg["PGUSER"] and pg["PGDATABASE"]:

                data["database_url"] = (
                    f"postgresql://{quote_plus(pg['PGUSER'])}:"
                    f"{quote_plus(pg['PGPASSWORD'] or '')}@{pg['PGHOST']}"
                    f":{pg.get('PGPORT') or 5432}/{pg['PGDATABASE']}"
                    f"?sslmode={pg.get('PGSSLMODE') or 'prefer'}"
                )

        return data

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()