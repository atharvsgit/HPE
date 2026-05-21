"""
llm_hooks.py — Lightweight orchestration glue layer.

This module is the ONLY integration point between the violation aggregation/dispatch
pipeline and the LLM enrichment system. It enqueues Celery tasks and provides
lightweight stubs for future extension points.

Rules:
  - Provider logic MUST NOT live here (it belongs in services/llm/).
  - This module must remain import-safe even when Celery/Redis are unavailable.
  - All enqueue failures are caught and logged; they never block rule execution.
"""
from __future__ import annotations

import logging

from app.models.requests import RuleExecutionRequest
from app.models.responses import AIEnrichment

logger = logging.getLogger(__name__)


def enqueue_batch_dispatch(batch_id: int, rule: RuleExecutionRequest) -> bool:
    """
    Enqueues a Celery task to handle LLM enrichment and notification dispatch
    for the given violation batch.

    This is the PRIMARY integration point called by aggregator.py and dispatcher.py
    instead of directly calling notify_admin_of_failure.

    Returns True if the task was successfully enqueued, False otherwise.
    The caller should handle False as a signal to fall back to direct dispatch.
    """
    try:
        # Import here to avoid module-level Celery connection at import time.
        # This keeps the aggregator/dispatcher importable even without Redis.
        from app.daemon.worker import process_batch_dispatch_task

        rule_dict = {
            "rule_id": rule.rule_id,
            "rule_name": rule.rule_name,
            "sql": rule.sql,
            "expected_result": {
                "type": rule.expected_result.type,
                "value": rule.expected_result.value,
            },
        }

        task = process_batch_dispatch_task.delay(batch_id, rule_dict)
        logger.info(
            "[ENQUEUE] Dispatched LLM enrichment task. batch_id=%s celery_task_id=%s",
            batch_id,
            task.id,
        )
        return True

    except Exception as exc:
        # Redis unavailable, Celery not configured, or broker error.
        # Log and signal fallback — never raise into the aggregator.
        logger.error(
            "[ENQUEUE FAILED] Could not enqueue dispatch task for batch_id=%s. "
            "Fallback to direct dispatch will be used. error=%s",
            batch_id,
            exc,
        )
        return False


async def enrich_batch_with_ai_summary(batch_id: int, rule: RuleExecutionRequest) -> AIEnrichment | None:
    """
    Extension hook: directly call LLM orchestrator for inline enrichment.
    Used as a fallback when Celery is unavailable, or in direct-dispatch paths.
    Provider logic lives in services/llm/orchestrator.py.
    """
    try:
        from app.services.llm.orchestrator import generate_batch_summary
        return await generate_batch_summary(batch_id)
    except Exception as exc:
        logger.error(
            "enrich_batch_with_ai_summary failed for batch_id=%s. error=%s",
            batch_id,
            exc,
        )
        return None


async def generate_fix_suggestions(batch_id: int, rule: RuleExecutionRequest) -> list[str]:
    """
    Extension hook: returns suggested fixes from a stored LLM summary if available.
    Future: call a dedicated fix-generation prompt via the LLM provider.
    """
    try:
        from app.services.llm.orchestrator import get_existing_summary
        enrichment = await get_existing_summary(batch_id)
        return enrichment.suggested_fixes if enrichment else []
    except Exception as exc:
        logger.error(
            "generate_fix_suggestions failed for batch_id=%s. error=%s",
            batch_id,
            exc,
        )
        return []


async def summarize_violation_batch(batch_id: int) -> str | None:
    """
    Extension hook: returns the AI summary text for a batch if one exists.
    Future: trigger a dedicated summarization prompt.
    """
    try:
        from app.services.llm.orchestrator import get_existing_summary
        enrichment = await get_existing_summary(batch_id)
        return enrichment.ai_summary if enrichment else None
    except Exception as exc:
        logger.error(
            "summarize_violation_batch failed for batch_id=%s. error=%s",
            batch_id,
            exc,
        )
        return None
