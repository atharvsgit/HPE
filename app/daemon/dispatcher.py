import asyncio
import logging
from datetime import datetime, UTC, timedelta

from sqlalchemy import text

from app.daemon.notifier import notify_admin_of_failure
from app.db.session import metadata_engine as db_engine
from app.models.requests import RuleExecutionRequest, ExpectedResult
from app.services.violations.llm_hooks import enqueue_batch_dispatch, enrich_batch_with_ai_summary

logger = logging.getLogger(__name__)


def _get_window_minutes(severity: str) -> int:
    if severity == "critical":
        return 0
    if severity == "high":
        return 15
    if severity == "medium":
        return 60
    if severity == "low":
        return 360
    return 60


async def dispatch_expired_batches() -> None:
    """Scans for open violation batches that have exceeded their aggregation window and dispatches them."""
    async with db_engine.connect() as conn:
        # Fetch all open batches
        result = await conn.execute(
            text(
                """
                SELECT id, rule_id, severity, first_seen
                FROM dq_results.violation_batches
                WHERE status = 'open'
                """
            )
        )
        open_batches = result.mappings().all()

    now = datetime.now(UTC)
    
    for batch in open_batches:
        window = _get_window_minutes(batch["severity"])
        # Ensure first_seen is timezone-aware for comparison
        first_seen = batch["first_seen"]
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=UTC)
            
        if now - first_seen >= timedelta(minutes=window):
            await _dispatch_single_batch(batch["id"], batch["rule_id"])


async def _dispatch_single_batch(batch_id: int, rule_id: int) -> None:
    # 1. Transition to 'dispatching' to prevent concurrent dispatch (if multiple dispatchers run)
    async with db_engine.begin() as conn:
        res = await conn.execute(
            text("UPDATE dq_results.violation_batches SET status = 'dispatching' WHERE id = :id AND status = 'open' RETURNING id"),
            {"id": batch_id}
        )
        if res.scalar_one_or_none() is None:
            return  # Someone else took it
            
        # 2. Fetch rule details to construct a pseudo-request/result for the notifier
        rule_row = (await conn.execute(
            text("SELECT database_connection_id, rule_name, sql_text, expected_result_type, expected_result_value FROM dq_config.dq_rules WHERE rule_id = :rule_id"),
            {"rule_id": rule_id}
        )).mappings().first()
        
    if not rule_row:
        # Rule deleted? Just resolve batch.
        async with db_engine.begin() as conn:
            await conn.execute(text("UPDATE dq_results.violation_batches SET status = 'resolved' WHERE id = :id"), {"id": batch_id})
        return

    # Mock a request for the existing raw notifier
    # The actual implementation of a batch notifier should ideally summarize the batch.
    # Future: LLM summary injection point here.
    pseudo_rule = RuleExecutionRequest(
        rule_id=rule_id,
        database_connection_id=rule_row["database_connection_id"],
        rule_name=rule_row["rule_name"],
        sql=rule_row["sql_text"],
        expected_result=ExpectedResult(
            type=rule_row["expected_result_type"],
            value=rule_row["expected_result_value"]
        )
    )

    # For the result, we can just pass a dummy result indicating a batch failure
    from app.models.responses import RuleExecutionResult
    pseudo_result = RuleExecutionResult(
        rule_id=rule_id,
        database_connection_id=rule_row["database_connection_id"],
        rule_name=rule_row["rule_name"],
        status="FAIL",
        result=None,
        violation_rows=[],
        expected_result=pseudo_rule.expected_result,
        execution_time_ms=0,
        executed_at=datetime.now(UTC),
        error=None
    )

    # --- Integration point: enqueue async Celery LLM enrichment task ---
    # llm_hooks.enqueue_batch_dispatch → worker.py → orchestrator.py → notifier
    rule_dict_for_worker = {
        "rule_id": rule_id,
        "rule_name": pseudo_rule.rule_name,
        "sql": pseudo_rule.sql,
        "expected_result": {
            "type": pseudo_rule.expected_result.type,
            "value": pseudo_rule.expected_result.value,
        },
    }
    enqueued = enqueue_batch_dispatch(batch_id, pseudo_rule)
    if enqueued:
        logger.info("Batch %s enqueued for async LLM dispatch.", batch_id)
        # Worker owns the status transition; return here.
        return

    # --- Fallback: Celery unavailable, dispatch inline ---
    logger.warning("Celery unavailable. Falling back to inline dispatch for batch %s.", batch_id)
    ai_enrichment = await enrich_batch_with_ai_summary(batch_id, pseudo_rule)
    if ai_enrichment:
        pseudo_result.ai_enrichment = ai_enrichment

    try:
        await notify_admin_of_failure(pseudo_rule, pseudo_result)
        new_status = 'dispatched'
    except Exception as exc:
        logger.error("Failed to dispatch batch %s: %s", batch_id, exc)
        new_status = 'failed'

    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE dq_results.violation_batches SET status = :status WHERE id = :id"),
            {"status": new_status, "id": batch_id},
        )
        if new_status == 'dispatched':
            await conn.execute(
                text("UPDATE dq_results.violation_events SET status = 'dispatched' WHERE rule_id = :rule_id AND status = 'open'"),
                {"rule_id": rule_id},
            )


async def run_dispatcher_loop() -> None:
    logger.info("Starting Intelligent Alert Dispatcher Loop...")
    while True:
        try:
            await dispatch_expired_batches()
        except Exception as exc:
            logger.error(f"Error in dispatcher loop: {exc}")
        
        await asyncio.sleep(60)  # Check every minute


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_dispatcher_loop())
