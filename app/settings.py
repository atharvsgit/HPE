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
    # Database connections (Atharv — Validation & Rule Management)
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

    # Notifications (Parnika)
    slack_webhook_url: str | None = os.getenv("SLACK_WEBHOOK_URL")
    smtp_server: str | None = os.getenv("SMTP_SERVER")
    smtp_port: int | None = _optional_int("SMTP_PORT", 587)
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    smtp_timeout_seconds: float = float(os.getenv("SMTP_TIMEOUT_SECONDS", "5"))
    notification_http_timeout_seconds: float = float(
        os.getenv("NOTIFICATION_HTTP_TIMEOUT_SECONDS", "5")
    )
    notification_email_from: str = os.getenv(
        "NOTIFICATION_EMAIL_FROM",
        "alerts@dataqualitydaemon.local",
    )
    admin_email: str | None = os.getenv("ADMIN_EMAIL")

    # LLM-assisted rule drafts
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock")
    llm_model: str = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    llm_api_key: str | None = os.getenv("LLM_API_KEY")
    llm_request_timeout_seconds: int = int(
        os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "30")
    )
    llm_dry_run_enabled: bool = os.getenv("LLM_DRY_RUN_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
    }

    # Platform Intelligence (Manjunath Patil)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    rule_suggestion_backend: str = os.getenv("RULE_SUGGESTION_BACKEND", "heuristic")
    profiling_row_limit: int = int(os.getenv("PROFILING_ROW_LIMIT", "100000"))
    anomaly_contamination: float = float(os.getenv("ANOMALY_CONTAMINATION", "0.05"))
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    pipeline_execution_jitter_seconds: int = int(
        os.getenv("PIPELINE_EXECUTION_JITTER_SECONDS", "120")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
