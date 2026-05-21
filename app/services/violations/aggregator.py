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
from app.services.violations.llm_hooks import enqueue_batch_dispatch, enrich_batch_with_ai_summary
from app.services.violations.policies import get_or_create_policy

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

    # 5. Critical violations trigger immediately
    if severity == "critical" and not is_duplicate:
        await _dispatch_batch_immediately(batch_id, rule, result)
        

async def _dispatch_batch_immediately(batch_id: int, rule: RuleExecutionRequest, result: RuleExecutionResult) -> None:
    """
    Handles immediate dispatch for critical-severity violations.

    Preferred path: enqueue a Celery task so LLM enrichment runs async.
    Fallback: inline enrichment + direct notify if Celery/Redis is unavailable.
    The batch status is NOT marked dispatched here — the worker owns that transition.
    """
    # --- Preferred: async Celery dispatch (non-blocking) ---
    # Integration point: llm_hooks.enqueue_batch_dispatch → Celery → worker.py
    enqueued = enqueue_batch_dispatch(batch_id, rule)
    if enqueued:
        logger.info(
            "Critical batch %s enqueued for async LLM dispatch.", batch_id
        )
        return

    # --- Fallback: Celery unavailable, dispatch synchronously ---
    logger.warning(
        "Celery unavailable. Falling back to inline dispatch for critical batch %s.", batch_id
    )
    ai_enrichment = await enrich_batch_with_ai_summary(batch_id, rule)
    if ai_enrichment:
        result.ai_enrichment = ai_enrichment

    try:
        await notify_admin_of_failure(rule, result)
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE dq_results.violation_batches SET status = 'dispatched' WHERE id = :id"),
                {"id": batch_id},
            )
            await conn.execute(
                text("UPDATE dq_results.violation_events SET status = 'dispatched' WHERE rule_id = :rule_id AND status = 'open'"),
                {"rule_id": rule.rule_id},
            )
    except Exception as exc:
        logger.error("Failed to dispatch critical batch %s: %s", batch_id, exc)
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE dq_results.violation_batches SET status = 'failed' WHERE id = :id"),
                {"id": batch_id},
            )
