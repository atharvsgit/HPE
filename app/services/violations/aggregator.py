import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.daemon.notifier import notify_admin_of_failure
from app.db.session import metadata_engine as db_engine
from app.models.requests import RuleExecutionRequest
from app.models.responses import RuleExecutionResult
from app.services.violations.deduplicator import check_duplicate_and_increment, generate_fingerprint
from app.services.violations.llm_hooks import enrich_batch_with_ai_summary
from app.services.violations.policies import get_or_create_policy
from app.services.violations.alert_context import attach_alert_context

logger = logging.getLogger(__name__)


async def process_violation(rule: RuleExecutionRequest, result: RuleExecutionResult) -> None:
    """
    Entrypoint for intelligent violation aggregation.
    Decides whether to notify immediately, batch, or suppress based on policy and history.
    """
    if result.status not in {"FAIL", "ERROR"}:
        return

    # 1. Fetch severity
    rule_id = result.rule_id
    if not rule_id:
        # Ad-hoc rule executions don't have a rule_id and shouldn't be batched.
        # Fallback to direct raw notification.
        await notify_admin_of_failure(rule, result)
        return

    async with db_engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT severity FROM dq_config.dq_rules WHERE rule_id = :rule_id"),
            {"rule_id": rule_id}
        )).mappings().first()
        severity = row["severity"] if row else "medium"

    # 2. Fetch notification policy
    policy = await get_or_create_policy(rule_id)

    # 3. Deduplication
    fingerprint = generate_fingerprint(rule_id, result.status, result.violation_rows)
    is_duplicate = await check_duplicate_and_increment(rule_id, fingerprint, policy.deduplication_window_minutes)

    # 4. Handle Batches and Events
    observed_value = result.result.get("violation_count") if result.result else None
    
    async with db_engine.begin() as conn:
        # If it's a new event, record it
        if not is_duplicate:
            await conn.execute(
                text(
                    """
                    INSERT INTO dq_results.violation_events (
                        rule_result_id, rule_id, severity, violation_count, sample_rows, fingerprint
                    )
                    VALUES (
                        NULL, :rule_id, :severity, :violation_count, :sample_rows, :fingerprint
                    )
                    """
                ),
                {
                    "rule_id": rule_id,
                    "severity": severity,
                    "violation_count": observed_value,
                    "sample_rows": json.dumps(result.violation_rows) if result.violation_rows else None,
                    "fingerprint": fingerprint
                }
            )

        if is_duplicate:
            batch_row = (await conn.execute(
                text(
                    """
                    SELECT id FROM dq_results.violation_batches 
                    WHERE rule_id = :rule_id
                    ORDER BY first_seen DESC
                    LIMIT 1
                    """
                ),
                {"rule_id": rule_id}
            )).scalar_one_or_none()
        else:
            batch_row = (await conn.execute(
                text(
                    """
                    SELECT id FROM dq_results.violation_batches 
                    WHERE rule_id = :rule_id AND status = 'open'
                    LIMIT 1
                    """
                ),
                {"rule_id": rule_id}
            )).scalar_one_or_none()

        if batch_row is not None:
            # Update existing batch
            await conn.execute(
                text(
                    """
                    UPDATE dq_results.violation_batches
                    SET last_seen = NOW(),
                        total_occurrences = total_occurrences + 1,
                        total_violation_count = COALESCE(total_violation_count, 0) + COALESCE(:violation_count, 0)
                    WHERE id = :batch_id
                    """
                ),
                {"batch_id": batch_row, "violation_count": observed_value}
            )
            batch_id = batch_row
        else:
            # Create new batch
            batch_id = (await conn.execute(
                text(
                    """
                    INSERT INTO dq_results.violation_batches (
                        rule_id, severity, first_seen, last_seen, total_occurrences, total_violation_count
                    )
                    VALUES (
                        :rule_id, :severity, NOW(), NOW(), 1, :violation_count
                    )
                    RETURNING id
                    """
                ),
                {"rule_id": rule_id, "severity": severity, "violation_count": observed_value}
            )).scalar_one()

    # 5. New failures trigger notifications immediately. Duplicate failures are
    # still aggregated to avoid repeatedly notifying on channels that already
    # received this incident. If a user enables a new channel while the incident
    # is still inside the dedupe window, dispatch only that missing channel.
    dispatch_rule = rule
    should_dispatch = not is_duplicate
    if is_duplicate:
        missing_channels = await _missing_requested_channels(rule, batch_id)
        if missing_channels:
            dispatch_rule = rule.model_copy(update={"notification_channels": missing_channels})
            should_dispatch = True

    if should_dispatch:
        await attach_alert_context(
            result,
            rule_id=rule_id,
            batch_id=batch_id,
            deduplication_window_minutes=policy.deduplication_window_minutes,
        )
        await _dispatch_batch_immediately(batch_id, dispatch_rule, result)
        

async def _dispatch_batch_immediately(batch_id: int, rule: RuleExecutionRequest, result: RuleExecutionResult) -> None:
    """
    Handles immediate dispatch for a newly opened violation batch.

    The current prototype performs inline enrichment and notification delivery
    for newly opened batches. The dispatcher module owns the async Celery path
    for expired batches.
    """
    ai_enrichment = await enrich_batch_with_ai_summary(batch_id, rule)
    if ai_enrichment:
        result.ai_enrichment = ai_enrichment

    try:
        outcome = await notify_admin_of_failure(rule, result)
        new_status = "dispatched" if outcome.any_sent else "failed"
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE dq_results.violation_batches SET status = :status WHERE id = :id"),
                {"status": new_status, "id": batch_id},
            )
            if outcome.any_sent:
                await conn.execute(
                    text("UPDATE dq_results.violation_events SET status = 'dispatched' WHERE rule_id = :rule_id AND status = 'open'"),
                    {"rule_id": rule.rule_id},
                )
    except Exception as exc:
        logger.error("Failed to dispatch violation batch %s: %s", batch_id, exc)
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE dq_results.violation_batches SET status = 'failed' WHERE id = :id"),
                {"id": batch_id},
            )


async def _missing_requested_channels(rule: RuleExecutionRequest, batch_id: int) -> list[str]:
    requested_channels = list(dict.fromkeys(rule.notification_channels or ["slack", "email"]))
    if not requested_channels:
        return []

    async with db_engine.connect() as conn:
        batch_started_at = (await conn.execute(
            text(
                """
                SELECT first_seen
                FROM dq_results.violation_batches
                WHERE id = :batch_id
                """
            ),
            {"batch_id": batch_id},
        )).scalar_one_or_none()

        if batch_started_at is None:
            return requested_channels

        sent_rows = (await conn.execute(
            text(
                """
                SELECT DISTINCT channel
                FROM dq_results.notification_deliveries
                WHERE rule_id = :rule_id
                  AND status = 'sent'
                  AND sent_at >= :batch_started_at
                """
            ),
            {"rule_id": rule.rule_id, "batch_started_at": batch_started_at},
        )).mappings().all()

    sent_channels = {row["channel"] for row in sent_rows}
    return [channel for channel in requested_channels if channel not in sent_channels]
