from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.db.session import metadata_engine
from app.settings import get_settings


APP_SETTING_KEYS = {
    "ai_provider",
    "ai_model",
    "ai_api_key",
    "admin_email",
    "notification_email_from",
    "smtp_server",
    "smtp_port",
    "smtp_username",
    "smtp_password",
    "smtp_use_tls",
    "slack_webhook_url",
    "slack_bot_token",
    "slack_channel",
}


SECRET_KEYS = {
    "ai_api_key",
    "smtp_password",
    "slack_webhook_url",
    "slack_bot_token",
}


PROVIDER_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "openrouter": "openai/gpt-4o-mini",
    "groq": "llama3-8b-8192",
}


PROVIDERS = tuple(PROVIDER_DEFAULT_MODELS.keys())


@dataclass(frozen=True)
class RuntimeNotificationSettings:
    slack_webhook_url: str | None
    slack_bot_token: str | None
    slack_channel: str | None
    smtp_server: str | None
    smtp_port: int | None
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool
    smtp_timeout_seconds: float
    notification_http_timeout_seconds: float
    notification_email_from: str
    admin_email: str | None


@dataclass(frozen=True)
class RuntimeAISettings:
    provider: str
    model: str
    api_key: str


async def ensure_app_settings_table() -> None:
    async with metadata_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_config.app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                is_secret BOOLEAN NOT NULL DEFAULT false,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE, DELETE ON dq_config.app_settings TO dq_app
        """))


async def get_settings_payload() -> dict[str, Any]:
    await ensure_app_settings_table()
    values = await _load_values()
    settings = get_settings()

    provider = (values.get("ai_provider") or "gemini").lower()
    if provider not in PROVIDERS:
        provider = "gemini"
    model = values.get("ai_model") or _env_model_for_provider(provider) or PROVIDER_DEFAULT_MODELS[provider]
    ai_key = values.get("ai_api_key") or _env_key_for_provider(provider) or ""

    smtp_port = _int_value(values.get("smtp_port"), settings.smtp_port)
    smtp_use_tls = _bool_value(values.get("smtp_use_tls"), settings.smtp_use_tls)
    smtp_password = values.get("smtp_password") or settings.smtp_password or ""
    slack_webhook = values.get("slack_webhook_url") or settings.slack_webhook_url or ""
    slack_bot_token = values.get("slack_bot_token") or settings.slack_bot_token or ""
    slack_channel = values.get("slack_channel") or settings.slack_channel or ""

    return {
        "ai": {
            "provider": provider,
            "model": model,
            "has_api_key": bool(ai_key),
            "masked_api_key": _mask_secret(ai_key),
            "providers": [
                {"id": key, "label": _provider_label(key), "default_model": default_model}
                for key, default_model in PROVIDER_DEFAULT_MODELS.items()
            ],
        },
        "notifications": {
            "admin_email": values.get("admin_email") or settings.admin_email or "",
            "notification_email_from": values.get("notification_email_from") or settings.notification_email_from,
            "smtp_server": values.get("smtp_server") or settings.smtp_server or "",
            "smtp_port": smtp_port,
            "smtp_username": values.get("smtp_username") or settings.smtp_username or "",
            "smtp_use_tls": smtp_use_tls,
            "has_smtp_password": bool(smtp_password),
            "masked_smtp_password": _mask_secret(smtp_password),
            "slack_configured": bool(slack_webhook or (slack_bot_token and slack_channel)),
            "masked_slack_webhook": _mask_secret(slack_webhook),
        },
    }


async def save_ai_settings(provider: str, model: str | None, api_key: str | None) -> dict[str, Any]:
    provider = provider.lower().strip()
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported AI provider: {provider}")
    await ensure_app_settings_table()
    values: dict[str, str] = {
        "ai_provider": provider,
        "ai_model": (model or PROVIDER_DEFAULT_MODELS[provider]).strip(),
    }
    if api_key is not None and api_key.strip():
        values["ai_api_key"] = api_key.strip()
    await _upsert_values(values)
    return await get_settings_payload()


async def save_notification_settings(payload: dict[str, Any]) -> dict[str, Any]:
    await ensure_app_settings_table()
    allowed = {
        "admin_email",
        "notification_email_from",
        "smtp_server",
        "smtp_port",
        "smtp_username",
        "smtp_password",
        "smtp_use_tls",
        "slack_webhook_url",
    }
    values: dict[str, str] = {}
    for key in allowed:
        if key not in payload:
            continue
        value = payload[key]
        if key in {"smtp_password", "slack_webhook_url"} and (value is None or str(value).strip() == ""):
            continue
        if value is None:
            values[key] = ""
        elif key == "smtp_use_tls":
            values[key] = "true" if bool(value) else "false"
        else:
            values[key] = str(value).strip()
    await _upsert_values(values)
    return await get_settings_payload()


async def get_runtime_ai_settings() -> RuntimeAISettings:
    await ensure_app_settings_table()
    values = await _load_values()
    provider = (values.get("ai_provider") or "gemini").lower()
    if provider not in PROVIDERS:
        provider = "gemini"
    return RuntimeAISettings(
        provider=provider,
        model=values.get("ai_model") or _env_model_for_provider(provider) or PROVIDER_DEFAULT_MODELS[provider],
        api_key=values.get("ai_api_key") or _env_key_for_provider(provider) or "",
    )


async def get_runtime_notification_settings() -> RuntimeNotificationSettings:
    await ensure_app_settings_table()
    values = await _load_values()
    settings = get_settings()
    return RuntimeNotificationSettings(
        slack_webhook_url=values.get("slack_webhook_url") or settings.slack_webhook_url,
        slack_bot_token=values.get("slack_bot_token") or settings.slack_bot_token,
        slack_channel=values.get("slack_channel") or settings.slack_channel,
        smtp_server=values.get("smtp_server") or settings.smtp_server,
        smtp_port=_int_value(values.get("smtp_port"), settings.smtp_port),
        smtp_username=values.get("smtp_username") or settings.smtp_username,
        smtp_password=values.get("smtp_password") or settings.smtp_password,
        smtp_use_tls=_bool_value(values.get("smtp_use_tls"), settings.smtp_use_tls),
        smtp_timeout_seconds=settings.smtp_timeout_seconds,
        notification_http_timeout_seconds=settings.notification_http_timeout_seconds,
        notification_email_from=values.get("notification_email_from") or settings.notification_email_from,
        admin_email=values.get("admin_email") or settings.admin_email,
    )


async def _load_values() -> dict[str, str]:
    async with metadata_engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT setting_key, setting_value
            FROM dq_config.app_settings
        """))).mappings().all()
    return {row["setting_key"]: row["setting_value"] for row in rows if row["setting_value"] is not None}


async def _upsert_values(values: dict[str, str]) -> None:
    if not values:
        return
    async with metadata_engine.begin() as conn:
        for key, value in values.items():
            if key not in APP_SETTING_KEYS:
                continue
            await conn.execute(
                text("""
                    INSERT INTO dq_config.app_settings (setting_key, setting_value, is_secret, updated_at)
                    VALUES (:key, :value, :is_secret, NOW())
                    ON CONFLICT (setting_key)
                    DO UPDATE SET setting_value = EXCLUDED.setting_value,
                                  is_secret = EXCLUDED.is_secret,
                                  updated_at = NOW()
                """),
                {"key": key, "value": value, "is_secret": key in SECRET_KEYS},
            )


def _env_key_for_provider(provider: str) -> str:
    settings = get_settings()
    env_keys = {
        "gemini": settings.gemini_api_key,
        "groq": settings.groq_api_key,
        "openai": os.getenv("OPENAI_API_KEY", ""),
        "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
        "openrouter": os.getenv("OPENROUTER_API_KEY", ""),
    }
    return env_keys.get(provider, "") or ""


def _env_model_for_provider(provider: str) -> str:
    settings = get_settings()
    env_models = {
        "gemini": settings.gemini_model,
        "groq": settings.llm_model,
        "openai": os.getenv("OPENAI_MODEL", ""),
        "anthropic": os.getenv("ANTHROPIC_MODEL", ""),
        "openrouter": os.getenv("OPENROUTER_MODEL", ""),
    }
    return env_models.get(provider, "") or ""


def _int_value(value: str | None, default: int | None) -> int | None:
    if value in {None, ""}:
        return default
    try:
        return int(str(value))
    except ValueError:
        return default


def _bool_value(value: str | None, default: bool) -> bool:
    if value in {None, ""}:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def _mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _provider_label(provider: str) -> str:
    return {
        "gemini": "Gemini",
        "openai": "OpenAI",
        "anthropic": "Claude / Anthropic",
        "openrouter": "OpenRouter",
        "groq": "Groq",
    }.get(provider, provider)
