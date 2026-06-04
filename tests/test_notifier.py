from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.daemon.notifier import _slack_response_payload, notify_admin_of_failure
from app.models.requests import ExpectedResult, RuleExecutionRequest
from app.models.responses import AlertContext, ErrorDetail, RuleExecutionResult


class NotificationSettings:
    slack_webhook_url = "http://slack.test"
    slack_bot_token = None
    slack_channel = None
    smtp_server = "smtp.test"
    smtp_port = 587
    smtp_username = "user"
    smtp_password = "password"
    smtp_use_tls = True
    smtp_timeout_seconds = 3
    notification_http_timeout_seconds = 3
    notification_email_from = "alerts@test.local"
    admin_email = "admin@test.com"


@pytest.fixture
def base_rule() -> RuleExecutionRequest:
    return RuleExecutionRequest(
        rule_name="No active employee has negative salary",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE salary < 0;",
        expected_result=ExpectedResult(type="zero_violations"),
    )


@pytest.fixture
def failed_result(base_rule: RuleExecutionRequest) -> RuleExecutionResult:
    return RuleExecutionResult(
        rule_id=1,
        rule_name=base_rule.rule_name,
        status="FAIL",
        result={"violation_count": 10},
        violation_rows=[{"employee_id": 1, "salary": -1000}],
        expected_result=base_rule.expected_result,
        execution_time_ms=12,
        executed_at=datetime.now(UTC),
        error=None,
    )


def attach_alert_context(result: RuleExecutionResult) -> None:
    result._alert_context = AlertContext(
        batch_id=99,
        deduplication_window_minutes=15,
        recent_failure_count=10,
        recent_observed_total=100,
        window_started_at=datetime(2026, 6, 4, 13, 3, tzinfo=UTC),
        window_ended_at=datetime(2026, 6, 4, 13, 18, tzinfo=UTC),
        batch_occurrences=10,
        batch_violation_count=100,
    )


@pytest.fixture(autouse=True)
def no_delivery_db_writes(monkeypatch) -> None:
    async def fake_record_delivery(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.daemon.notifier._record_delivery", fake_record_delivery)


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=NotificationSettings())
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_notifies_slack_and_email_on_failure(
    mock_smtp_class,
    mock_httpx_post,
    _mock_get_settings,
    base_rule,
    failed_result,
) -> None:
    attach_alert_context(failed_result)
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_httpx_post.return_value = mock_response
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    outcome = await notify_admin_of_failure(base_rule, failed_result)

    mock_httpx_post.assert_called_once()
    assert mock_httpx_post.call_args.args[0] == "http://slack.test"
    slack_payload = mock_httpx_post.call_args.kwargs["json"]["text"]
    assert "DATA QUALITY RULE FAIL ALERT" in slack_payload
    assert "Recent failed executions: 10 executions in the last 15 minutes." in slack_payload
    assert "Recent observed violation total: 100" in slack_payload
    assert "Current alert batch: Violation batch ID: 99, 10 occurrences, batch violation total: 100" in slack_payload
    assert "VIOLATION ROWS PREVIEW" in slack_payload
    assert "employee_id | salary" in slack_payload
    assert "1           | -1000" in slack_payload

    mock_smtp_class.assert_called_once_with("smtp.test", 587, timeout=3)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("user", "password")
    mock_smtp_instance.send_message.assert_called_once()
    sent_message = mock_smtp_instance.send_message.call_args.args[0]
    assert sent_message["Subject"] == "Data Quality Alert: No active employee has negative salary"
    assert sent_message["To"] == "admin@test.com"

    assert sent_message.is_multipart()
    payloads = list(sent_message.walk())
    content_types = [part.get_content_type() for part in payloads]
    assert "text/plain" in content_types
    assert "text/html" in content_types
    assert "text/csv" in content_types

    text_body = next(part.get_content() for part in payloads if part.get_content_type() == "text/plain")
    assert "DATA QUALITY RULE FAIL ALERT" in text_body
    assert "RECENT FAILURE SUMMARY" in text_body
    assert "Recent failed executions: 10 executions in the last 15 minutes." in text_body
    assert "VIOLATION ROWS PREVIEW" in text_body
    assert "employee_id | salary" in text_body

    html_body = next(part.get_content() for part in payloads if part.get_content_type() == "text/html")
    assert "<!DOCTYPE html>" in html_body
    assert "No active employee has negative salary" in html_body
    assert "Recent Failure Summary" in html_body
    assert "Recent failed executions: 10 executions in the last 15 minutes." in html_body
    assert "employee_id" in html_body
    assert "salary" in html_body

    csv_attachment = next(part for part in payloads if part.get_content_type() == "text/csv")
    assert csv_attachment.get_filename() == "rule_1_violations.csv"
    assert "employee_id,salary" in csv_attachment.get_content()
    assert outcome.attempted == 2
    assert outcome.sent == 2
    assert outcome.failed == 0


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=NotificationSettings())
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_respects_rule_notification_channels(
    mock_smtp_class,
    mock_httpx_post,
    _mock_get_settings,
    base_rule,
    failed_result,
) -> None:
    base_rule.notification_channels = ["slack"]
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_httpx_post.return_value = mock_response

    outcome = await notify_admin_of_failure(base_rule, failed_result)

    mock_httpx_post.assert_called_once()
    mock_smtp_class.assert_not_called()
    assert outcome.any_sent
    assert outcome.attempted == 1


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings")
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_slack_violation_upload_suppresses_duplicate_webhook_message(
    mock_smtp_class,
    mock_httpx_post,
    mock_get_settings,
    base_rule,
    failed_result,
) -> None:
    attach_alert_context(failed_result)

    class UploadSettings(NotificationSettings):
        slack_bot_token = "xoxb-test"
        slack_channel = "C123"
        smtp_server = None

    slack_client = MagicMock()
    slack_client.files_upload_v2 = AsyncMock(return_value={"ok": True})
    mock_get_settings.return_value = UploadSettings()

    with patch("app.daemon.notifier.AsyncWebClient", return_value=slack_client) as mock_slack_client:
        outcome = await notify_admin_of_failure(base_rule, failed_result)

    mock_slack_client.assert_called_once_with(token="xoxb-test")
    slack_client.files_upload_v2.assert_awaited_once()
    upload_kwargs = slack_client.files_upload_v2.call_args.kwargs
    assert upload_kwargs["channel"] == "C123"
    assert upload_kwargs["title"] == f"Violation Rows - {base_rule.rule_name}"
    assert "Recent failed executions: 10 executions in the last 15 minutes." in upload_kwargs["initial_comment"]
    assert "Recent observed violation total: 100" in upload_kwargs["initial_comment"]
    assert "employee_id,salary" in upload_kwargs["content"]
    mock_httpx_post.assert_not_called()
    mock_smtp_class.assert_not_called()
    assert outcome.any_sent


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings")
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_slack_bot_upload_without_webhook_is_not_skipped(
    mock_smtp_class,
    mock_httpx_post,
    mock_get_settings,
    base_rule,
    failed_result,
) -> None:
    class BotOnlySettings(NotificationSettings):
        slack_webhook_url = None
        slack_bot_token = "xoxb-test"
        slack_channel = "C123"
        smtp_server = None

    slack_client = MagicMock()
    slack_client.files_upload_v2 = AsyncMock(return_value={"ok": True})
    mock_get_settings.return_value = BotOnlySettings()

    with patch("app.daemon.notifier.AsyncWebClient", return_value=slack_client) as mock_slack_client:
        outcome = await notify_admin_of_failure(base_rule, failed_result)

    mock_slack_client.assert_called_once_with(token="xoxb-test")
    slack_client.files_upload_v2.assert_awaited_once()
    mock_httpx_post.assert_not_called()
    mock_smtp_class.assert_not_called()
    assert outcome.any_sent
    assert outcome.sent == 1
    assert outcome.failed == 0


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings")
async def test_logs_when_no_notification_channels_configured(
    mock_get_settings,
    base_rule,
    failed_result,
    caplog,
) -> None:
    class EmptySettings:
        slack_webhook_url = None
        smtp_server = None

    mock_get_settings.return_value = EmptySettings()

    with caplog.at_level("WARNING"):
        outcome = await notify_admin_of_failure(base_rule, failed_result)

    assert "no notification channels are configured" in caplog.text
    assert not outcome.any_sent
    assert outcome.skipped == 2


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=NotificationSettings())
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_does_not_notify_on_pass(
    mock_smtp_class,
    mock_httpx_post,
    _mock_get_settings,
    base_rule,
) -> None:
    result = RuleExecutionResult(
        rule_id=1,
        rule_name=base_rule.rule_name,
        status="PASS",
        result={"violation_count": 0},
        expected_result=base_rule.expected_result,
        execution_time_ms=12,
        executed_at=datetime.now(UTC),
        error=None,
    )

    outcome = await notify_admin_of_failure(base_rule, result)

    mock_httpx_post.assert_not_called()
    mock_smtp_class.assert_not_called()
    assert not outcome.any_sent


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=NotificationSettings())
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_notifies_on_error(
    _mock_smtp_class,
    mock_httpx_post,
    _mock_get_settings,
    base_rule,
) -> None:
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_httpx_post.return_value = mock_response
    result = RuleExecutionResult(
        rule_id=1,
        rule_name=base_rule.rule_name,
        status="ERROR",
        result=None,
        expected_result=base_rule.expected_result,
        execution_time_ms=12,
        executed_at=datetime.now(UTC),
        error=ErrorDetail(type="SQL_EXECUTION_ERROR", message="database error"),
    )

    await notify_admin_of_failure(base_rule, result)

    assert "database error" in mock_httpx_post.call_args.kwargs["json"]["text"]


def test_slack_response_payload_supports_async_slack_response_shape() -> None:
    class SlackResponse:
        data = {"ok": True, "file": {"id": "F123"}}

    assert _slack_response_payload(SlackResponse()) == {"ok": True, "file": {"id": "F123"}}
