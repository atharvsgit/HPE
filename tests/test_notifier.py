from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.daemon.notifier import notify_admin_of_failure
from app.models.requests import ExpectedResult, RuleExecutionRequest
from app.models.responses import ErrorDetail, RuleExecutionResult


class NotificationSettings:
    smtp_server = "smtp.test"
    smtp_port = 587
    smtp_username = "user"
    smtp_password = "password"
    smtp_use_tls = True
    smtp_timeout_seconds = 3
    notification_email_from = "alerts@test.local"
    admin_email = "manjunathpatil3155@gmail.com"


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


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=NotificationSettings())
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_sends_email_on_failure(
    mock_smtp_class,
    _mock_get_settings,
    base_rule,
    failed_result,
) -> None:
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance

    await notify_admin_of_failure(base_rule, failed_result)

    mock_smtp_class.assert_called_once_with("smtp.test", 587, timeout=3)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("user", "password")
    mock_smtp_instance.send_message.assert_called_once()
    sent_message = mock_smtp_instance.send_message.call_args.args[0]
    assert sent_message["Subject"] == "Data Quality Alert: No active employee has negative salary"
    assert sent_message["To"] == "manjunathpatil3155@gmail.com"
    assert "DATA QUALITY RULE ALERT" in sent_message.get_content()
    assert "Violation rows preview" in sent_message.get_content()


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings")
async def test_logs_when_no_notification_channels_configured(
    mock_get_settings,
    base_rule,
    failed_result,
    caplog,
) -> None:
    class EmptySettings:
        smtp_server = None

    mock_get_settings.return_value = EmptySettings()

    with caplog.at_level("WARNING"):
        await notify_admin_of_failure(base_rule, failed_result)

    assert "email notifications are not configured" in caplog.text


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=NotificationSettings())
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_does_not_notify_on_pass(
    mock_smtp_class,
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

    await notify_admin_of_failure(base_rule, result)

    mock_smtp_class.assert_not_called()


@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=NotificationSettings())
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_notifies_on_error(
    mock_smtp_class,
    _mock_get_settings,
    base_rule,
) -> None:
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
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

    sent_message = mock_smtp_instance.send_message.call_args.args[0]
    assert "database error" in sent_message.get_content()
