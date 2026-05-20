from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage

from app.models.requests import RuleExecutionRequest
from app.models.responses import RuleExecutionResult
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _notification_text(rule: RuleExecutionRequest, result: RuleExecutionResult) -> str:
    lines = [
        "DATA QUALITY RULE ALERT",
        f"Rule: {rule.rule_name}",
        f"Status: {result.status}",
        f"Rule ID: {rule.rule_id if rule.rule_id is not None else 'ad hoc'}",
    ]

    if result.result is not None:
        lines.append(f"Observed: {result.result}")

    if result.violation_rows:
        preview_count = min(len(result.violation_rows), 5)
        preview = json.dumps(result.violation_rows[:preview_count], default=str)
        lines.append(f"Violation rows preview ({preview_count} shown): {preview}")

    lines.append(f"Expected: {rule.expected_result.type}")
    if rule.expected_result.value is not None:
        lines.append(f"Expected value: {rule.expected_result.value}")

    if result.error is not None:
        lines.append(f"Error: {result.error.type}: {result.error.message}")

    lines.append(f"Executed at: {result.executed_at.isoformat()}")

    return "\n".join(lines)


def _send_email_notification_sync(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
    settings: Settings,
) -> None:
    if not settings.smtp_server or not settings.smtp_port or not settings.admin_email:
        logger.warning(
            "Email alert skipped: SMTP_SERVER, SMTP_PORT, or ADMIN_EMAIL is missing."
        )
        return

    message = EmailMessage()
    message["Subject"] = f"Data Quality Alert: {rule.rule_name}"
    message["From"] = settings.notification_email_from
    message["To"] = settings.admin_email
    message.set_content(_notification_text(rule, result))

    try:
        with smtplib.SMTP(
            settings.smtp_server,
            settings.smtp_port,
            timeout=settings.smtp_timeout_seconds,
        ) as server:
            if settings.smtp_use_tls:
                server.starttls()

            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)

            server.send_message(message)
        logger.info("Sent data quality alert email for rule %s.", rule.rule_name)
    except Exception as exc:
        logger.error("Failed to send email data quality alert: %s", exc)


async def _send_email_notification(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
    settings: Settings,
) -> None:
    await asyncio.to_thread(_send_email_notification_sync, rule, result, settings)


async def notify_admin_of_failure(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
) -> None:
    if result.status not in {"FAIL", "ERROR"}:
        return

    settings = get_settings()
    tasks = []

    if settings.smtp_server:
        tasks.append(_send_email_notification(rule, result, settings))

    if not tasks:
        logger.warning(
            "Rule %s ended with %s, but email notifications are not configured.",
            rule.rule_name,
            result.status,
        )
        return

    await asyncio.gather(*tasks)
