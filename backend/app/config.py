from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve .env relative to this file so the path is correct regardless of
# which directory the process is launched from (app server, alembic, tests).
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    database_url: str
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    selection_token_expire_minutes: int = 5

    class Config:
        env_file = str(_ENV_FILE)


settings = Settings()
