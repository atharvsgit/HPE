from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.schedule_preview import build_schedule_preview


def test_schedule_preview_returns_next_run_in_multiple_timezones(monkeypatch):
    class SettingsStub:
        scheduler_timezone = "Asia/Kolkata"

    monkeypatch.setattr("app.services.schedule_preview.get_settings", lambda: SettingsStub())

    preview = build_schedule_preview(
        "40 18 * * *",
        now=datetime(2026, 6, 3, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )

    assert preview is not None
    assert preview["scheduler_timezone"] == "Asia/Kolkata"
    assert preview["cron"] == "40 18 * * *"
    assert any(item["timezone"] == "Asia/Kolkata" and "IST" in item["display"] for item in preview["timezones"])
    assert any(item["timezone"] == "UTC" and "UTC" in item["display"] for item in preview["timezones"])


def test_schedule_preview_is_empty_for_manual_schedule():
    assert build_schedule_preview(None) is None
