from pydantic_settings import BaseSettings
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
    class Config:
        env_file = "../.env"
settings = Settings()
