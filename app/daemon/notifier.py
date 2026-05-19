import logging
import smtplib
import asyncio
import httpx
from email.message import EmailMessage

from app.models.requests import RuleExecutionRequest
from app.models.responses import RuleExecutionResult
from app.settings import get_settings

logger = logging.getLogger(__name__)

async def _send_slack_notification(rule: RuleExecutionRequest, result: RuleExecutionResult, webhook_url: str) -> None:
    rule_name = rule.rule_name or "Ad-hoc Rule"
    message = f"*ALERT: DATA QUALITY RULE VIOLATION*\n*Rule*: {rule_name}\n*Status*: {result.status}"
    
    if result.status == "FAIL":
        message += f"\n*Expected*: {rule.expected_result.type}\n*Observed*: {result.result}"
    elif result.error:
        message += f"\n*Error*: {result.error.message}"

    try:
        async with httpx.AsyncClient() as client:
            payload = {"text": message}
            response = await client.post(webhook_url, json=payload, timeout=5.0)
            response.raise_for_status()
            logger.info("Successfully sent Slack notification.")
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")

def _send_email_notification_sync(rule: RuleExecutionRequest, result: RuleExecutionResult, settings) -> None:
    if not (settings.smtp_server and settings.smtp_port and settings.admin_email):
        logger.warning("Email notification skipped: missing SMTP_SERVER, SMTP_PORT, or ADMIN_EMAIL")
        return

    rule_name = rule.rule_name or "Ad-hoc Rule"
    
    msg = EmailMessage()
    msg['Subject'] = f"Data Quality Alert: {rule_name}"
    msg['From'] = "alerts@dataqualitydaemon.local"
    msg['To'] = settings.admin_email
    
    body = f"Rule Violation Detected!\n\nRule: {rule_name}\nStatus: {result.status}\n"
    if result.status == "FAIL":
        body += f"Observed Result: {result.result}"
    elif result.error:
        body += f"Error Message: {result.error.message}"
        
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            # We wrap in try-except for starttls and login in case the server doesn't support/require it
            try:
                server.starttls()
            except smtplib.SMTPException:
                pass
                
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
                
            server.send_message(msg)
        logger.info("Successfully sent Email notification.")
    except Exception as e:
        logger.error(f"Failed to send Email notification: {e}")

async def _send_email_notification(rule: RuleExecutionRequest, result: RuleExecutionResult, settings) -> None:
    # Run the synchronous smtplib in a threadpool
    await asyncio.to_thread(_send_email_notification_sync, rule, result, settings)

async def notify_admin_of_failure(rule: RuleExecutionRequest, result: RuleExecutionResult) -> None:
    """
    Sends a notification to the administrator when a rule fails.
    Dispatches to configured channels (Slack, Email) simultaneously.
    """
    if result.status not in ("FAIL", "ERROR"):
        return

    settings = get_settings()
    
    tasks = []
    
    if settings.slack_webhook_url:
        tasks.append(_send_slack_notification(rule, result, settings.slack_webhook_url))
        
    if settings.smtp_server:
        tasks.append(_send_email_notification(rule, result, settings))
        
    if tasks:
        # Run all configured notifications concurrently
        await asyncio.gather(*tasks)
    else:
        # Fallback if no channels are configured
        rule_name = rule.rule_name or "Ad-hoc Rule"
        logger.warning(f"Rule Failed ({rule_name}) but NO notification channels are configured!")
