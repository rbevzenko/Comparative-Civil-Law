from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # postgresql+asyncpg://user:pass@host:5432/dbname
    database_url: str
    api_token: str

    s3_endpoint_url: str
    s3_region: str = "eu-central-1"
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket_name: str
    s3_presigned_url_expiry_seconds: int = 3600

    # Two shared access passwords for the /ui/* web interface (session-cookie
    # login, not HTTP Basic — see app/web/auth.py). Two, not one, so the
    # password can be rotated per person without sharing a single secret.
    ui_password_1: str
    ui_password_2: str
    # Signing key for the session cookie (starlette SessionMiddleware).
    session_secret_key: str

    db_pool_size: int = 5
    db_max_overflow: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
