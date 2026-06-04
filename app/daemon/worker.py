"""
Celery Worker — LLM Enrichment Dispatcher.

This module defines the Celery application and the single task
`process_batch_dispatch_task` which:

  1. Acquires the batch (idempotency guard via 'dispatching' status lock).
  2. Attempts LLM enrichment via the orchestrator (if LLM_ENABLED).
  3. Transitions batch status: open → dispatching → enriched → dispatched
                                                              → failed
  4. Sends notification (enriched or plain fallback).

The dispatcher can enqueue this worker for asynchronous enrichment. Some
prototype paths still fall back to inline enrichment when the queue is not used.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, UTC
from decimal import Decimal

from celery import Celery
from celery.utils.log import get_task_logger
from sqlalchemy import text

from app.settings import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Celery application — broker is Redis, backend is also Redis for task state.
# Only used for async dispatch orchestration and enrichment jobs.
# ---------------------------------------------------------------------------
celery_app = Celery(
    "dq_llm_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_broker_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,           # Ack only after task completes (retry safety)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker process
    task_track_started=True,
)

task_logger = get_task_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    return asyncio.run(_run_and_close(coro))


async def _run_and_close(coro):
    try:
        return await coro
    finally:
        from app.db.session import close_db_engine

        await close_db_engine()


@celery_app.task(
    bind=True,
    name="dq.process_batch_dispatch",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    rate_limit="10/m",
    soft_time_limit=20,
    time_limit=30,
)
def process_batch_dispatch_task(self, batch_id: int, rule_dict: dict) -> None:
    """
    Main enrichment and dispatch task.
    """
    # Create a correlation prefix for all logs in this task
    cid = f"[CID batch:{batch_id} rule:{rule_dict.get('rule_id')} task:{self.request.id}]"
    
    task_logger.info("%s [TASK START] process_batch_dispatch", cid)
    t_start = time.monotonic()

    try:
        _run_async(_execute_dispatch(self, batch_id, rule_dict, cid))
    except Exception as exc:
        task_logger.error("%s [TASK ERROR] error=%s", cid, exc, exc_info=True)
        raise self.retry(exc=exc)
    finally:
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        task_logger.info("%s [TASK END] elapsed_ms=%s", cid, elapsed_ms)


async def _execute_dispatch(task, batch_id: int, rule_dict: dict, cid: str) -> None:
    """Async implementation of the dispatch task logic."""
    from app.db.session import metadata_engine as db_engine
    from app.models.requests import RuleExecutionRequest, ExpectedResult
    from app.models.responses import RuleExecutionResult
    from app.daemon.notifier import notify_admin_of_failure
    from app.services.llm.orchestrator import generate_batch_summary
    from app.services.violations.alert_context import attach_alert_context

    expected = rule_dict.get("expected_result", {})
    pseudo_rule = RuleExecutionRequest(
        rule_id=rule_dict["rule_id"],
        database_connection_id=rule_dict.get("database_connection_id"),
        rule_name=rule_dict["rule_name"],
        sql=rule_dict.get("sql", ""),
        expected_result=ExpectedResult(
            type=expected.get("type", "zero_violations"),
            value=expected.get("value"),
        ),
        notification_channels=rule_dict.get("notification_channels") or ["slack", "email"],
    )
    async with db_engine.connect() as conn:
        batch_row = (await conn.execute(
            text(
                """
                SELECT total_violation_count
                FROM dq_results.violation_batches
                WHERE id = :batch_id
                """
            ),
            {"batch_id": batch_id},
        )).mappings().first()
        event_row = (await conn.execute(
            text(
                """
                SELECT sample_rows
                FROM dq_results.violation_events
                WHERE rule_id = :rule_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"rule_id": rule_dict["rule_id"]},
        )).mappings().first()

    violation_count = _json_number(batch_row["total_violation_count"]) if batch_row else None
    violation_rows = _parse_sample_rows(event_row["sample_rows"]) if event_row else []

    pseudo_result = RuleExecutionResult(
        rule_id=rule_dict["rule_id"],
        database_connection_id=rule_dict.get("database_connection_id"),
        rule_name=rule_dict["rule_name"],
        status="FAIL",
        result={"violation_count": violation_count} if violation_count is not None else None,
        violation_rows=violation_rows,
        expected_result=pseudo_rule.expected_result,
        execution_time_ms=0,
        executed_at=datetime.now(UTC),
        error=None,
    )
    await attach_alert_context(
        pseudo_result,
        rule_id=rule_dict["rule_id"],
        batch_id=batch_id,
    )

    # --- Acquire dispatching lock (idempotency: allow open or dispatching if it's a retry) ---
    async with db_engine.begin() as conn:
        locked = (await conn.execute(
            text(
                "UPDATE dq_results.violation_batches "
                "SET status = 'dispatching' "
                "WHERE id = :id AND status IN ('open', 'dispatching') "
                "RETURNING id"
            ),
            {"id": batch_id},
        )).scalar_one_or_none()

    if locked is None:
        task_logger.warning("%s [IDEMPOTENCY] Batch already past 'open/dispatching'. Skipping duplicate.", cid)
        return

    # --- LLM Enrichment (non-blocking; fallback on any failure) ---
    task_logger.info("%s [LLM START] Requesting enrichment", cid)
    t_llm = time.monotonic()
    ai_enrichment = None

    try:
        ai_enrichment = await generate_batch_summary(batch_id)
        llm_latency_ms = int((time.monotonic() - t_llm) * 1000)

        if ai_enrichment:
            task_logger.info("%s [LLM SUCCESS] llm_latency_ms=%s", cid, llm_latency_ms)
            pseudo_result.ai_enrichment = ai_enrichment

            # Transition to enriched status
            async with db_engine.begin() as conn:
                await conn.execute(
                    text("UPDATE dq_results.violation_batches SET status = 'enriched' WHERE id = :id"),
                    {"id": batch_id},
                )
        else:
            task_logger.info(
                "%s [LLM FALLBACK] No enrichment available. Proceeding with plain notification. llm_latency_ms=%s",
                cid, llm_latency_ms
            )
    except Exception as exc:
        task_logger.error(
            "%s [LLM FALLBACK] LLM enrichment raised unexpected error: %s. Dispatching plain notification.",
            cid, exc
        )

    # --- Notify and preserve failed delivery state for operator visibility. ---
    new_status: str
    try:
        outcome = await notify_admin_of_failure(pseudo_rule, pseudo_result)
        new_status = "dispatched" if outcome.any_sent else "failed"
        if outcome.any_sent:
            task_logger.info("%s [NOTIFY SUCCESS]", cid)
        else:
            task_logger.error("%s [NOTIFY FAILED] no channels delivered", cid)
    except Exception as exc:
        task_logger.error("%s [NOTIFY FAILED] error=%s", cid, exc)
        new_status = "failed"
        
        # Mark as failed in DB before raising to allow introspection, though retry might reset to dispatching.
        async with db_engine.begin() as conn:
            await conn.execute(
                text("UPDATE dq_results.violation_batches SET status = 'failed' WHERE id = :id"),
                {"id": batch_id},
            )
        raise  # Trigger Celery retry for transient network failure

    # --- Final status update ---
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE dq_results.violation_batches SET status = :status WHERE id = :id"),
            {"status": new_status, "id": batch_id},
        )
        if new_status == "dispatched":
            await conn.execute(
                text(
                    "UPDATE dq_results.violation_events "
                    "SET status = 'dispatched' "
                    "WHERE rule_id = :rule_id AND status = 'open'"
                ),
                {"rule_id": rule_dict["rule_id"]},
            )


def _json_number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value


def _parse_sample_rows(value) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
    else:
        parsed = value
    return parsed if isinstance(parsed, list) else []
