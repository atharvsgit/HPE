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
    # -------------------------------------------------------------------------
    # Database connections (Atharv — Validation & Rule Management)
    # -------------------------------------------------------------------------
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
    rule_execution_jitter_seconds: int = int(
        os.getenv("RULE_EXECUTION_JITTER_SECONDS", "120")
    )

    # -------------------------------------------------------------------------
    # Platform Intelligence (Manjunath Patil)
    # -------------------------------------------------------------------------

    # Gemini AI configuration
    # Get your key from https://aistudio.google.com/
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    # Rule suggestion backend: "heuristic" (no API key needed) or "gemini"
    rule_suggestion_backend: str = os.getenv("RULE_SUGGESTION_BACKEND", "heuristic")

    # Maximum rows to load when profiling a table (prevents memory issues on large tables)
    profiling_row_limit: int = int(os.getenv("PROFILING_ROW_LIMIT", "100000"))

    # Isolation Forest / LOF contamination parameter (expected proportion of anomalies)
    anomaly_contamination: float = float(os.getenv("ANOMALY_CONTAMINATION", "0.05"))

    # Gemini model name (can be overridden for testing with faster/cheaper models)
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Jitter for recurring full-pipeline schedules to avoid synchronized load spikes
    pipeline_execution_jitter_seconds: int = int(
        os.getenv("PIPELINE_EXECUTION_JITTER_SECONDS", "120")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
