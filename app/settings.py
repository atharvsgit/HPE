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


def _optional_int(name: str, default: int | None = None) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    return int(raw_value)


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
    rule_execution_jitter_seconds: int = int(os.getenv("RULE_EXECUTION_JITTER_SECONDS", "120"))
    slack_webhook_url: str | None = os.getenv("SLACK_WEBHOOK_URL")
    slack_bot_token: str | None = os.getenv("SLACK_BOT_TOKEN")
    slack_channel: str | None = os.getenv("SLACK_CHANNEL")
    smtp_server: str | None = os.getenv("SMTP_SERVER")
    smtp_port: int | None = _optional_int("SMTP_PORT", 587)
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}
    smtp_timeout_seconds: float = float(os.getenv("SMTP_TIMEOUT_SECONDS", "5"))
    notification_http_timeout_seconds: float = float(
        os.getenv("NOTIFICATION_HTTP_TIMEOUT_SECONDS", "5")
    )
    notification_email_from: str = os.getenv(
        "NOTIFICATION_EMAIL_FROM",
        "alerts@dataqualitydaemon.local",
    )
    admin_email: str | None = os.getenv("ADMIN_EMAIL")

    # -------------------------------------------------------------------------
    # Intelligent Alert Dispatcher (LLM Enrichment)
    # -------------------------------------------------------------------------
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "llama3-8b-8192")
    llm_enabled: bool = os.getenv("LLM_ENABLED", "false").lower() in {"1", "true", "yes"}
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
