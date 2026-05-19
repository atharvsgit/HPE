import pytest
from apscheduler.triggers.cron import CronTrigger

from app.daemon.cron import (
    CronValidationError,
    SchedulerStatus,
    classify_scheduler_status,
    cron_to_trigger,
    validate_cron_expression,
)


@pytest.mark.parametrize(
    "cron_expression",
    [
        "*/5 * * * *",
        "0 0 * * *",
        "0 2 * * 1",
        "0 3 1 * *",
        "0 4 1 6 *",
    ],
)
def test_valid_cron_parsing(cron_expression: str) -> None:
    validate_cron_expression(cron_expression)

    assert isinstance(cron_to_trigger(cron_expression), CronTrigger)


@pytest.mark.parametrize(
    "cron_expression",
    [
        "* * * *",
        "61 * * * *",
        "* 25 * * *",
        "not a cron expression",
    ],
)
def test_invalid_cron_rejection(cron_expression: str) -> None:
    with pytest.raises(CronValidationError):
        validate_cron_expression(cron_expression)


def test_scheduler_status_classification() -> None:
    assert (
        classify_scheduler_status(is_enabled=True, schedule_cron="*/5 * * * *")
        == SchedulerStatus.SCHEDULABLE
    )
    assert (
        classify_scheduler_status(is_enabled=False, schedule_cron="*/5 * * * *")
        == SchedulerStatus.DISABLED
    )
    assert (
        classify_scheduler_status(is_enabled=True, schedule_cron=None)
        == SchedulerStatus.MISSING_SCHEDULE
    )
    assert (
        classify_scheduler_status(is_enabled=True, schedule_cron="invalid")
        == SchedulerStatus.INVALID_CRON
    )
