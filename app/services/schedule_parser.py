from __future__ import annotations

import re


def parse_schedule_to_cron(text_value: str | None) -> str | None:
    if not text_value:
        return None

    text = text_value.strip().lower()
    if text in {"manual", "none", "do not schedule", "run manually"}:
        return None

    number = _first_number(text) or 1

    if "minute" in text:
        return "* * * * *" if number <= 1 else f"*/{min(number, 59)} * * * *"
    if "hour" in text:
        return "0 * * * *" if number <= 1 else f"0 */{min(number, 23)} * * *"
    if "day" in text or "daily" in text:
        return "0 9 * * *" if number <= 1 else f"0 9 */{min(number, 31)} * *"
    if "week" in text or "weekly" in text:
        return "0 9 * * 1" if number <= 1 else f"0 9 * * 1"
    if "month" in text or "monthly" in text:
        return "0 9 1 * *"

    if text.startswith("*/") or len(text.split()) == 5:
        return text

    return None


def _first_number(text: str) -> int | None:
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
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return int(match.group(1))
    for word, value in word_numbers.items():
        if re.search(rf"\b{word}\b", text):
            return value
    return None
