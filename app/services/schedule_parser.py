from __future__ import annotations

import re


class ScheduleParseError(ValueError):
    pass


def parse_schedule_to_cron(text_value: str | None) -> str | None:
    if not text_value:
        return None

    text = text_value.strip().lower()
    if text in {"manual", "none", "do not schedule", "run manually"}:
        return None

    if "minute" in text:
        number = _interval_number(text, "minute") or 1
        if number < 1 or number > 59:
            raise ScheduleParseError("Minute schedules must use an interval from 1 to 59 minutes.")
        return "* * * * *" if number <= 1 else f"*/{min(number, 59)} * * * *"
    if "hour" in text:
        number = _interval_number(text, "hour") or 1
        if number < 1 or number > 23:
            raise ScheduleParseError("Hourly schedules must use an interval from 1 to 23 hours.")
        return "0 * * * *" if number <= 1 else f"0 */{min(number, 23)} * * *"
    if "day" in text or "daily" in text:
        number = _interval_number(text, "day") or 1
        if number < 1 or number > 31:
            raise ScheduleParseError("Daily schedules must use an interval from 1 to 31 days.")
        hour, minute = _time_from_text(text) or (9, 0)
        day_field = "*" if number <= 1 else f"*/{min(number, 31)}"
        return f"{minute} {hour} {day_field} * *"
    if "week" in text or "weekly" in text:
        hour, minute = _time_from_text(text) or (9, 0)
        return f"{minute} {hour} * * 1"
    if "month" in text or "monthly" in text:
        hour, minute = _time_from_text(text) or (9, 0)
        return f"{minute} {hour} 1 * *"

    if text.startswith("*/") or len(text.split()) == 5:
        return text

    return None


def _interval_number(text: str, unit: str) -> int | None:
    number_pattern = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    match = re.search(rf"\bevery\s+(?:{number_pattern}\s+)?{unit}s?\b", text)
    if match is None:
        return None
    raw_value = match.group(1)
    if raw_value is None:
        return 1
    return _number_value(raw_value)


def _number_value(raw_value: str) -> int | None:
    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    if raw_value.isdigit():
        return int(raw_value)
    return word_numbers.get(raw_value)


def _time_from_text(text: str) -> tuple[int, int] | None:
    match = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
    if match is None:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)

    if minute > 59:
        return None
    if meridiem:
        if hour < 1 or hour > 12:
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return None

    return hour, minute
