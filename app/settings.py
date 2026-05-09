import os
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import BaseModel


def _postgres_url(username: str, password_env: str) -> str:
    password = quote_plus(os.getenv(password_env, ""))
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "dq_test")
    return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"


class Settings(BaseModel):
    database_url: str = os.getenv(
        "DATABASE_URL",
        _postgres_url("dq_executor", "DQ_EXECUTOR_PASSWORD"),
    )
    metadata_database_url: str = os.getenv(
        "METADATA_DATABASE_URL",
        _postgres_url("dq_app", "DQ_APP_PASSWORD"),
    )
    statement_timeout_ms: int = int(os.getenv("STATEMENT_TIMEOUT_MS", "15000"))
    pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    pool_recycle: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))
    rule_execution_jitter_seconds: int = int(os.getenv("RULE_EXECUTION_JITTER_SECONDS", "120"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
