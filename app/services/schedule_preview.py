from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from app.settings import get_settings


DEFAULT_PREVIEW_TIMEZONES = (
    "Asia/Kolkata",
    "UTC",
    "America/New_York",
    "Europe/London",
)


def build_schedule_preview(cron_expression: str | None, now: datetime | None = None) -> dict[str, object] | None:
    if cron_expression is None or not cron_expression.strip():
        return None

    scheduler_timezone = _safe_timezone(get_settings().scheduler_timezone)
    try:
        trigger = CronTrigger.from_crontab(cron_expression, timezone=scheduler_timezone)
    except ValueError:
        return None
    current_time = now or datetime.now(scheduler_timezone)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=scheduler_timezone)
    else:
        current_time = current_time.astimezone(scheduler_timezone)

    next_run = trigger.get_next_fire_time(None, current_time)
    if next_run is None:
        return None

    timezone_names = _unique_timezones([scheduler_timezone.key, *DEFAULT_PREVIEW_TIMEZONES])
    return {
        "scheduler_timezone": scheduler_timezone.key,
        "cron": cron_expression,
        "next_run_at": next_run,
        "timezones": [
            {
                "label": _timezone_label(timezone_name),
                "timezone": timezone_name,
                "next_run_at": next_run.astimezone(_safe_timezone(timezone_name)),
                "display": _format_time(next_run, timezone_name),
            }
            for timezone_name in timezone_names
        ],
    }


def _safe_timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _unique_timezones(timezone_names: list[str]) -> list[str]:
    unique_names: list[str] = []
    for timezone_name in timezone_names:
        if timezone_name not in unique_names:
            unique_names.append(timezone_name)
    return unique_names


def _timezone_label(timezone_name: str) -> str:
    labels = {
        "Asia/Kolkata": "IST",
        "UTC": "UTC",
        "America/New_York": "New York",
        "Europe/London": "London",
    }
    return labels.get(timezone_name, timezone_name)


def _format_time(value: datetime, timezone_name: str) -> str:
    localized = value.astimezone(_safe_timezone(timezone_name))
    return localized.strftime("%b %d, %Y, %I:%M %p %Z")
