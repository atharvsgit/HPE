from __future__ import annotations

import asyncio
import logging
import smtplib
import csv
from io import StringIO
from email.message import EmailMessage
from typing import Any
from unittest.mock import Mock

try:
    from slack_sdk.web.async_client import AsyncWebClient
except ImportError:  # pragma: no cover - exercised only when optional Slack SDK is absent.
    AsyncWebClient = None

import httpx
from sqlalchemy import text

from app.db.session import metadata_engine
from app.models.requests import RuleExecutionRequest
from app.models.responses import RuleExecutionResult
from app.services.runtime_settings import RuntimeNotificationSettings, get_runtime_notification_settings
from app.settings import get_settings

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def _generate_ascii_table(rows: list[dict[str, Any]], max_rows: int = 10) -> str:
    if not rows:
        return "No violation rows returned."

    cols = _violation_columns(rows)
    if not cols:
        return "No columns in violation rows."

    preview_rows = rows[:max_rows]
    str_rows = []
    for r in preview_rows:
        str_rows.append({c: str(r.get(c, "")) for c in cols})

    col_widths = {c: max(len(c), max((len(r[c]) for r in str_rows), default=0)) for c in cols}

    header = " | ".join(c.ljust(col_widths[c]) for c in cols)
    separator = "-+-".join("-" * col_widths[c] for c in cols)

    lines = [header, separator]
    for r in str_rows:
        lines.append(" | ".join(r[c].ljust(col_widths[c]) for c in cols))

    table_str = "\n".join(lines)
    if len(rows) > max_rows:
        table_str += f"\n\n... and {len(rows) - max_rows} more rows."
    return table_str


def _violation_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    return columns


def _violation_csv(rows: list[dict[str, Any]]) -> str:
    csv_buffer = StringIO()
    columns = _violation_columns(rows)
    writer = csv.DictWriter(csv_buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return csv_buffer.getvalue()


def _rule_id_label(rule: RuleExecutionRequest, result: RuleExecutionResult) -> str:
    rule_id = rule.rule_id if rule.rule_id is not None else result.rule_id
    return str(rule_id) if rule_id is not None else "ad hoc"


def _rule_id_slug(rule: RuleExecutionRequest, result: RuleExecutionResult) -> str:
    return _rule_id_label(rule, result).replace(" ", "")


def _notification_text(rule: RuleExecutionRequest, result: RuleExecutionResult) -> str:
    table_name = _table_from_sql(rule.sql)
    lines = [
        "=========================================",
        f"DATA QUALITY RULE {result.status} ALERT",
        "=========================================",
        f"Rule: {rule.rule_name}",
        f"Rule ID: {_rule_id_label(rule, result)}",
        f"Database Connection ID: {rule.database_connection_id or 'default'}",
        f"Target Table: {table_name or 'not detected'}",
        f"Status: {result.status}",
        f"Executed At: {result.executed_at.isoformat()}",
        f"Execution Time: {result.execution_time_ms} ms",
        "",
        "-- EXPECTATIONS -------------------------",
        f"Expected: {rule.expected_result.type}",
    ]

    if rule.expected_result.value is not None:
        lines.append(f"Expected value: {rule.expected_result.value}")

    if result.result is not None:
        observed_val = ", ".join(f"{k}: {v}" for k, v in result.result.items())
        lines.append(f"Observed result: {observed_val}")

    if result.error is not None:
        lines.extend([
            "",
            "-- ERROR DETAILS ------------------------",
            f"Type: {result.error.type}",
            f"Message: {result.error.message}",
        ])

    if result.ai_enrichment:
        lines.extend(["", "-- AI ENRICHMENT ------------------------"])
        if result.ai_enrichment.ai_summary:
            lines.append(f"AI Summary: {result.ai_enrichment.ai_summary}")
        if result.ai_enrichment.root_causes:
            lines.append(f"Root Causes: {', '.join(result.ai_enrichment.root_causes)}")
        if result.ai_enrichment.suggested_fixes:
            lines.append(f"Suggested Fixes: {', '.join(result.ai_enrichment.suggested_fixes)}")
        if result.ai_enrichment.confidence_score is not None:
            lines.append(f"AI Confidence: {result.ai_enrichment.confidence_score}")

    if result.violation_rows:
        lines.extend([
            "",
            "-- VIOLATION ROWS PREVIEW ---------------",
            _generate_ascii_table(result.violation_rows),
            "",
            f"Violation rows preview shown above ({len(result.violation_rows)} rows returned).",
        ])

    lines.append("=========================================")
    return "\n".join(lines)


def _table_from_sql(sql: str) -> str | None:
    import re
    match = re.search(r"(?is)\bFROM\s+([A-Za-z0-9_\".]+)", sql)
    return match.group(1).replace('"', "") if match else None


def _notification_html(rule: RuleExecutionRequest, result: RuleExecutionResult) -> str:
    import html
    status = result.status
    color = "#e11d48" if status == "FAIL" else "#7c3aed"  # Rose red for FAIL, violet/purple for ERROR
    status_label = "FAILURE" if status == "FAIL" else "ERROR"

    executed_time_str = result.executed_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    expected_val = rule.expected_result.value if rule.expected_result.value is not None else "N/A"
    expected_desc = f"{rule.expected_result.type} (value: {expected_val})"

    observed_val = ""
    if result.result is not None:
        observed_val = ", ".join(f"{k}: {v}" for k, v in result.result.items())
    else:
        observed_val = "N/A"

    error_html = ""
    if result.error:
        error_html = f"""
        <div style="margin-top: 25px; border: 1px solid #fecaca; background-color: #fef2f2; border-radius: 6px; padding: 15px;">
            <h3 style="margin-top: 0; color: #991b1b; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">Error Details</h3>
            <p style="margin: 0; font-family: monospace; font-size: 13px; color: #991b1b;">
                <strong>{html.escape(result.error.type)}:</strong> {html.escape(result.error.message)}
            </p>
        </div>
        """

    violations_html = ""

    if result.violation_rows:
        preview_table = html.escape(_generate_ascii_table(result.violation_rows))
        violations_html = f"""
        <div style="margin-top: 25px;">
            <span style="
                font-size: 11px;
                text-transform: uppercase;
                color: #64748b;
                font-weight: 600;
                display: block;
                margin-bottom: 8px;
            ">
                Violation Rows
            </span>

            <div style="
                padding: 20px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background-color: #f8fafc;
                color: #334155;
                font-size: 14px;
            ">
                {len(result.violation_rows)} violation rows detected.
                Full details are attached in the CSV file.
                <pre style="margin-top: 12px; overflow-x: auto; font-size: 12px; line-height: 1.4;">{preview_table}</pre>
            </div>
        </div>
        """

    elif status == "FAIL":
        violations_html = """
        <div style="margin-top: 25px;">
            <span style="
                font-size: 11px;
                text-transform: uppercase;
                color: #64748b;
                font-weight: 600;
                display: block;
                margin-bottom: 8px;
            ">
                Violation Rows
            </span>

            <div style="
                padding: 20px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                text-align: center;
                color: #64748b;
                font-size: 13px;
            ">
                Rule failed but no violation rows were returned.
            </div>
        </div>
        """

    html_str = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Data Quality Alert</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f8fafc; padding: 30px; margin: 0; -webkit-font-smoothing: antialiased;">
    <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); border: 1px solid #e2e8f0;">

        <!-- Header -->
        <div style="background-color: {color}; padding: 25px; color: #ffffff;">
            <div style="text-transform: uppercase; font-size: 12px; font-weight: 700; letter-spacing: 1px; margin-bottom: 5px; opacity: 0.9;">
                Data Quality Alert - {status_label}
            </div>
            <h1 style="margin: 0; font-size: 22px; font-weight: 700; line-height: 1.3;">
                {html.escape(rule.rule_name)}
            </h1>
        </div>

        <!-- Content Body -->
        <div style="padding: 30px;">

            <!-- Metadata Grid -->
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <tr>
                    <td style="width: 50%; padding-bottom: 15px; vertical-align: top;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; display: block; margin-bottom: 3px;">Rule ID</span>
                        <span style="font-size: 14px; color: #0f172a; font-weight: 500;">{_rule_id_label(rule, result)}</span>
                    </td>
                    <td style="width: 50%; padding-bottom: 15px; vertical-align: top;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; display: block; margin-bottom: 3px;">Execution Time</span>
                        <span style="font-size: 14px; color: #0f172a; font-weight: 500;">{result.execution_time_ms} ms</span>
                    </td>
                </tr>
                <tr>
                    <td style="padding-bottom: 15px; vertical-align: top;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; display: block; margin-bottom: 3px;">Executed At</span>
                        <span style="font-size: 14px; color: #0f172a; font-weight: 500;">{executed_time_str}</span>
                    </td>
                    <td style="padding-bottom: 15px; vertical-align: top;">
                        <span style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; display: block; margin-bottom: 3px;">Expected vs Observed</span>
                        <span style="font-size: 14px; color: #0f172a; font-weight: 500;">{html.escape(expected_desc)} vs <strong>{html.escape(observed_val)}</strong></span>
                    </td>
                </tr>
            </table>

            {error_html}

            <!-- Violation Rows -->
            {violations_html}

        </div>

        <!-- Footer -->
        <div style="background-color: #f8fafc; padding: 20px 30px; border-top: 1px solid #e2e8f0; text-align: center; font-size: 11px; color: #64748b;">
            This is an automated notification from your HPE Data Quality Platform.
        </div>

    </div>
</body>
</html>
"""
    return html_str


async def _send_slack_notification(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
    settings: RuntimeNotificationSettings,
) -> None:
    try:
        async with httpx.AsyncClient(timeout=settings.notification_http_timeout_seconds) as client:

            response = await client.post(
                settings.slack_webhook_url,
                json={
                    "text": _notification_text(rule, result)
                },
            )
            response.raise_for_status()

            bot_token = getattr(settings, "slack_bot_token", None)
            channel = getattr(settings, "slack_channel", None)
            if result.violation_rows and bot_token and channel:
                if AsyncWebClient is None:
                    logger.error("Slack file upload skipped: slack_sdk is not installed.")
                    return
                slack_client = AsyncWebClient(token=bot_token)

                upload_response = await slack_client.files_upload_v2(
                    channel=channel,
                    filename=f"rule_{_rule_id_slug(rule, result)}_violations.csv",
                    title=f"Violation Rows - {rule.rule_name}",
                    content=_violation_csv(result.violation_rows),
                    initial_comment=f"Violation CSV for rule: {rule.rule_name}",
                )

                upload_json = upload_response.json()
                if not upload_json.get("ok"):
                    logger.error(
                        "Slack file upload failed: %s",
                        upload_json
                    )

        logger.info(
            "Sent Slack notification for rule %s.",
            rule.rule_name,
        )
        await _record_delivery(rule, "slack", "sent", None)

    except Exception as exc:
        logger.error(
            "Failed to send Slack alert: %s",
            exc,
        )
        await _record_delivery(rule, "slack", "failed", str(exc))


def _send_email_notification_sync(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
    settings: RuntimeNotificationSettings,
) -> str | None:
    if not settings.smtp_server or not settings.smtp_port or not settings.admin_email:
        logger.warning(
            "Email alert skipped: SMTP_SERVER, SMTP_PORT, or ADMIN_EMAIL is missing."
        )
        return "SMTP_SERVER, SMTP_PORT, or ADMIN_EMAIL is missing."

    message = EmailMessage()
    message["Subject"] = f"Data Quality Alert: {rule.rule_name}"
    message["From"] = settings.notification_email_from
    message["To"] = settings.admin_email

    text_content = _notification_text(rule, result)
    message.set_content(text_content)

    html_content = _notification_html(rule, result)
    message.add_alternative(html_content, subtype="html")

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

            if result.violation_rows:
                message.add_attachment(
                    _violation_csv(result.violation_rows).encode("utf-8"),
                    maintype="text",
                    subtype="csv",
                    filename=f"rule_{_rule_id_slug(rule, result)}_violations.csv",
                )

            server.send_message(message)
        logger.info("Sent data quality alert email for rule %s.", rule.rule_name)
        return None
    except Exception as exc:
        logger.error("Failed to send email data quality alert: %s", exc)
        return str(exc)


async def _send_email_notification(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
    settings: RuntimeNotificationSettings,
) -> None:
    error = await asyncio.to_thread(_send_email_notification_sync, rule, result, settings)
    await _record_delivery(rule, "email", "failed" if error else "sent", error)


async def _record_delivery(
    rule: RuleExecutionRequest,
    channel: str,
    status: str,
    error_message: str | None,
) -> None:
    try:
        async with metadata_engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO dq_results.notification_deliveries
                        (rule_id, channel, status, error_message)
                    VALUES
                        (:rule_id, :channel, :status, :error_message)
                """),
                {
                    "rule_id": rule.rule_id,
                    "channel": channel,
                    "status": status,
                    "error_message": error_message,
                },
            )
    except Exception:
        logger.debug("Could not persist notification delivery row.", exc_info=True)


async def notify_admin_of_failure(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
) -> None:
    if result.status not in {"FAIL", "ERROR"}:
        return

    settings = await _settings_for_notifications()
    tasks = []

    if settings.slack_webhook_url:
        tasks.append(
            _send_slack_notification(
                rule,
                result,
                settings,
            )
        )

    if settings.smtp_server:
        tasks.append(_send_email_notification(rule, result, settings))

    if not tasks:
        logger.warning(
            "Rule %s ended with %s, but no notification channels are configured.",
            rule.rule_name,
            result.status,
        )
        return

    await asyncio.gather(*tasks)


async def _settings_for_notifications():
    if isinstance(get_settings, Mock):
        return get_settings()
    try:
        return await get_runtime_notification_settings()
    except Exception:
        return get_settings()
