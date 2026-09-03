from pydantic_settings import BaseSettings


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

    class Config:
        env_file = ".env"


settings = Settings()