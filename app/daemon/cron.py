from __future__ import annotations

from enum import StrEnum

from apscheduler.triggers.cron import CronTrigger


class CronValidationError(ValueError):
    pass


class SchedulerStatus(StrEnum):
    SCHEDULABLE = "schedulable"
    DISABLED = "disabled"
    MISSING_SCHEDULE = "missing_schedule"
    INVALID_CRON = "invalid_cron"


def cron_to_trigger(cron_expression: str) -> CronTrigger:
    validate_cron_expression(cron_expression)
    return CronTrigger.from_crontab(cron_expression, timezone="UTC")


def validate_cron_expression(cron_expression: str | None) -> None:
    if cron_expression is None:
        return

    normalized = cron_expression.strip()
    fields = normalized.split()
    if len(fields) != 5:
        raise CronValidationError(
            "schedule_cron must be a valid 5-field cron expression: "
            "minute hour day_of_month month day_of_week."
        )

    try:
        CronTrigger.from_crontab(normalized, timezone="UTC")
    except ValueError as exc:
        raise CronValidationError(f"Invalid schedule_cron: {exc}") from exc


def classify_scheduler_status(
    is_enabled: bool,
    schedule_cron: str | None,
) -> SchedulerStatus:
    if not is_enabled:
        return SchedulerStatus.DISABLED
    if schedule_cron is None or not schedule_cron.strip():
        return SchedulerStatus.MISSING_SCHEDULE
    try:
        validate_cron_expression(schedule_cron)
    except CronValidationError:
        return SchedulerStatus.INVALID_CRON
    return SchedulerStatus.SCHEDULABLE
