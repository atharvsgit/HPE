from __future__ import annotations

import asyncio
import json
import logging
import smtplib
import csv
from io import StringIO
from email.message import EmailMessage

import httpx

from app.models.requests import RuleExecutionRequest
from app.models.responses import RuleExecutionResult
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def _generate_ascii_table(rows: list[dict[str, Any]], max_rows: int = 10) -> str:
    if not rows:
        return "No violation rows returned."
    
    cols = list(rows[0].keys())
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


def _notification_text(rule: RuleExecutionRequest, result: RuleExecutionResult) -> str:
    lines = [
        "=========================================",
        f"DATA QUALITY RULE {result.status} ALERT",
        "=========================================",
        f"Rule: {rule.rule_name}",
        f"Rule ID: {rule.rule_id if rule.rule_id is not None else 'ad hoc'}",
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

    if result.violation_rows:
        lines.extend([
            "",
            f"Violation rows attached as CSV ({len(result.violation_rows)} rows)."
        ])

    lines.append("=========================================")
    return "\n".join(lines)


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
                Data Quality Alert • {status_label}
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
                        <span style="font-size: 14px; color: #0f172a; font-weight: 500;">{rule.rule_id if rule.rule_id is not None else 'ad hoc'}</span>
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
    settings: Settings,
) -> None:
    try:
        async with httpx.AsyncClient(timeout=settings.notification_http_timeout_seconds) as client:

            # Send normal Slack alert message

            await client.post(
                settings.slack_webhook_url,
                json={
                    "text": _notification_text(rule, result)
                },
            )

            # Upload CSV file if violation rows exist

            if result.violation_rows and settings.slack_bot_token and settings.slack_channel:

                csv_buffer = StringIO()

                writer = csv.DictWriter(
                    csv_buffer,
                    fieldnames=result.violation_rows[0].keys()
                )

                writer.writeheader()
                writer.writerows(result.violation_rows)

                csv_content = csv_buffer.getvalue()

                files = {
                    "file": (
                        f"rule_{rule.rule_id or 'adhoc'}_violations.csv",
                        csv_content,
                        "text/csv",
                    )
                }

                data = {
                    "channels": settings.slack_channel,
                    "initial_comment": (
                        f"Violation CSV for rule: {rule.rule_name}"
                    ),
                }

                headers = {
                    "Authorization": f"Bearer {settings.slack_bot_token}"
                }

                upload_response = await client.post(
                    "https://slack.com/api/files.upload",
                    headers=headers,
                    data=data,
                    files=files,
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

    except Exception as exc:
        logger.error(
            "Failed to send Slack alert: %s",
            exc,
        )


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

            # Attach violation rows as CSV
            if result.violation_rows:
                csv_buffer = StringIO()

                writer = csv.DictWriter(
                    csv_buffer,
                    fieldnames=result.violation_rows[0].keys()
                )

                writer.writeheader()
                writer.writerows(result.violation_rows)

                csv_content = csv_buffer.getvalue()

                message.add_attachment(
                    csv_content.encode("utf-8"),
                    maintype="text",
                    subtype="csv",
                    filename=f"rule_{rule.rule_id or 'adhoc'}_violations.csv",
                )

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

    if settings.slack_webhook_url:
        tasks.append(
            _send_slack_notification(
                _send_slack_notification(
                    rule,
                    result,
                    settings,
                )
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
