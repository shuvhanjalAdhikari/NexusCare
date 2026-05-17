from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode

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
    invite_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    password_reset_token_expire_minutes: int = 60   # 1 hour

    # Origins allowed to call the API from a browser. Supplied as a
    # comma-separated env var (CORS_ALLOWED_ORIGINS); the NoDecode marker
    # stops pydantic-settings from trying to JSON-decode that string so
    # the validator below can split it. The default covers the React
    # (3000) and Vite (5173) dev servers. Production MUST override this
    # with a strict whitelist of real frontend hostnames — never "*".
    cors_allowed_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_cors_allowed_origins(cls, value: object) -> object:
        """Split the comma-separated env string into a list. A real list
        (the in-code default) is passed through untouched."""
        if isinstance(value, str):
            return [
                origin.strip()
                for origin in value.split(",")
                if origin.strip()
            ]
        return value

    class Config:
        env_file = str(_ENV_FILE)


settings = Settings()
