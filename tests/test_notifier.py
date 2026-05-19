import logging
# pyrefly: ignore [missing-import]
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, UTC
from decimal import Decimal

from app.models.requests import RuleExecutionRequest, ExpectedResult
from app.models.responses import RuleExecutionResult, ErrorDetail
from app.daemon.notifier import notify_admin_of_failure

class MockSettings:
    slack_webhook_url = "http://slack.test"
    smtp_server = "smtp.test"
    smtp_port = 587
    smtp_username = "user"
    smtp_password = "password"
    admin_email = "admin@test.com"

@pytest.fixture
def base_rule():
    return RuleExecutionRequest(
        rule_name="Test Rule",
        sql="SELECT 1 as violation_count;",
        expected_result=ExpectedResult(type="zero_violations")
    )

@pytest.fixture
def fail_result(base_rule):
    return RuleExecutionResult(
        rule_id=1,
        rule_name=base_rule.rule_name,
        status="FAIL",
        result={"violation_count": 1},
        expected_result=base_rule.expected_result,
        execution_time_ms=10,
        executed_at=datetime.now(UTC),
        error=None
    )

@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=MockSettings())
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.daemon.notifier.smtplib.SMTP")
async def test_dual_notification_on_fail(mock_smtp_class, mock_httpx_post, mock_get_settings, base_rule, fail_result):
    # Mock SMTP context manager
    mock_smtp_instance = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
    
    await notify_admin_of_failure(base_rule, fail_result)
    
    # Verify Slack
    mock_httpx_post.assert_called_once()
    assert mock_httpx_post.call_args[0][0] == "http://slack.test"
    assert "DATA QUALITY RULE VIOLATION" in mock_httpx_post.call_args[1]["json"]["text"]
    
    # Verify Email
    mock_smtp_instance.send_message.assert_called_once()
    msg = mock_smtp_instance.send_message.call_args[0][0]
    assert msg["Subject"] == "Data Quality Alert: Test Rule"
    assert msg["To"] == "admin@test.com"

@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings")
async def test_no_config_fallback_log(mock_get_settings, base_rule, fail_result, caplog):
    # Empty settings
    class EmptySettings:
        slack_webhook_url = None
        smtp_server = None

    mock_get_settings.return_value = EmptySettings()
    
    with caplog.at_level(logging.WARNING):
        await notify_admin_of_failure(base_rule, fail_result)
        
    assert "but NO notification channels are configured!" in caplog.text

@pytest.mark.asyncio
@patch("app.daemon.notifier.get_settings", return_value=MockSettings())
@patch("app.daemon.notifier.httpx.AsyncClient.post", new_callable=AsyncMock)
async def test_do_not_notify_on_pass(mock_httpx_post, mock_get_settings, base_rule):
    result = RuleExecutionResult(
        rule_id=1,
        rule_name=base_rule.rule_name,
        status="PASS",
        result={"violation_count": 0},
        expected_result=base_rule.expected_result,
        execution_time_ms=10,
        executed_at=datetime.now(UTC),
        error=None
    )
    
    await notify_admin_of_failure(base_rule, result)
    
    # Neither slack nor email should be called
    mock_httpx_post.assert_not_called()
