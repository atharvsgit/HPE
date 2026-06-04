import pytest

from app.services.schedule_parser import ScheduleParseError, parse_schedule_to_cron


def test_daily_at_specific_time_parses_to_cron():
    assert parse_schedule_to_cron("daily at 10:30 am") == "30 10 * * *"


def test_every_day_at_specific_time_parses_to_cron():
    assert parse_schedule_to_cron("every day at 10:30 am") == "30 10 * * *"


def test_daily_time_does_not_become_interval():
    assert parse_schedule_to_cron("daily at 10:30 pm") == "30 22 * * *"


@pytest.mark.parametrize(
    "schedule_text",
    [
        "every 90 minutes",
        "every 24 hours",
        "every 32 days",
    ],
)
def test_unsupported_intervals_are_rejected(schedule_text):
    with pytest.raises(ScheduleParseError):
        parse_schedule_to_cron(schedule_text)
