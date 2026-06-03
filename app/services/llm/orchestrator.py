"""
LLM Orchestrator.

Central coordination layer between the Celery worker and the LLM provider.
Responsible for:
  - Fetching batch context from the database
  - Building sanitized prompt payloads
  - Calling the provider
  - Parsing and validating the response
  - Persisting the result to dq_results.llm_summaries
  - Returning an AIEnrichment object (or None on failure)

This module does NOT handle notification dispatch or batch status updates.
Those remain the responsibility of the Celery task in worker.py.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import text

from app.db.session import metadata_engine as db_engine
from app.models.responses import AIEnrichment
from app.services.llm import parser as llm_parser
from app.services.llm.prompts.summarization import SYSTEM_PROMPT, build_summarization_prompt
from app.services.llm.providers.groq_provider import GroqProvider
from app.settings import get_settings

logger = logging.getLogger(__name__)


async def _fetch_batch_context(batch_id: int) -> dict[str, Any] | None:
    """Fetches batch metadata and recent violation events for the given batch."""
    async with db_engine.connect() as conn:
        batch_row = (await conn.execute(
            text("""
                SELECT vb.id, vb.rule_id, vb.severity, vb.total_occurrences, vb.total_violation_count,
                       r.rule_name, r.sql_text
                FROM dq_results.violation_batches vb
                JOIN dq_config.dq_rules r ON r.rule_id = vb.rule_id
                WHERE vb.id = :batch_id
            """),
            {"batch_id": batch_id},
        )).mappings().first()

        if not batch_row:
            return None

        # Fetch recent sample rows from violation events (last 5)
        events = (await conn.execute(
            text("""
                SELECT sample_rows, violation_count, created_at
                FROM dq_results.violation_events
                WHERE rule_id = :rule_id
                ORDER BY created_at DESC
                LIMIT 5
            """),
            {"rule_id": batch_row["rule_id"]},
        )).mappings().all()

    sample_rows: list[dict] = []
    for ev in events:
        if ev["sample_rows"]:
            try:
                parsed = json.loads(ev["sample_rows"]) if isinstance(ev["sample_rows"], str) else ev["sample_rows"]
                sample_rows.extend(parsed[:2])  # max 2 rows per event
            except (json.JSONDecodeError, TypeError):
                pass

    # Build a trend summary from occurrences
    trend_summary = (
        f"This rule has triggered {batch_row['total_occurrences']} time(s) in this batch "
        f"with a total of {batch_row['total_violation_count'] or 0} cumulative violations."
    )

    return {
        "batch_id": batch_row["id"],
        "rule_id": batch_row["rule_id"],
        "rule_name": batch_row["rule_name"],
        "severity": batch_row["severity"],
        "violation_count": batch_row["total_violation_count"],
        "sample_rows": sample_rows[:5],  # hard cap
        "trend_summary": trend_summary,
    }


async def _get_historical_human_correction(rule_id: int) -> dict | None:
    """Fetches the most recent human-edited or accepted summary for the rule."""
    async with db_engine.connect() as conn:
        row = (await conn.execute(
            text("""
                SELECT f.edited_summary, f.edited_fixes, f.user_id, f.feedback_type, s.summary as original_summary
                FROM dq_results.llm_feedback f
                JOIN dq_results.violation_batches b ON b.id = f.violation_batch_id
                JOIN dq_results.llm_summaries s ON s.id = f.llm_summary_id
                WHERE b.rule_id = :rule_id
                AND f.feedback_type IN ('edit', 'accept', 'annotate')
                AND (f.edited_summary IS NOT NULL OR f.feedback_type = 'accept')
                ORDER BY f.created_at DESC
                LIMIT 1
            """),
            {"rule_id": rule_id},
        )).mappings().first()
        return dict(row) if row else None


async def _persist_summary(
    batch_id: int,
    parsed: dict[str, Any],
    raw_response: str,
) -> None:
    """Persists a validated LLM summary to dq_results.llm_summaries."""
    from app.services.llm.prompts.summarization import PROMPT_VERSION
    
    meta = parsed.get("_meta", {})
    provider_name = meta.get("provider_name")
    model_name = meta.get("model_name")
    token_usage = meta.get("token_usage")
    
    async with db_engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO dq_results.llm_summaries
                    (violation_batch_id, summary, root_causes, suggested_fixes, business_impact, raw_response, 
                     prompt_version, effective_confidence, provider_name, model_name, token_usage, parsing_failure)
                VALUES
                    (:batch_id, :summary, :root_causes, :suggested_fixes, :business_impact, :raw_response,
                     :prompt_version, :confidence, :provider_name, :model_name, :token_usage, :parsing_failure)
            """),
            {
                "batch_id": batch_id,
                "summary": parsed.get("summary", ""),
                "root_causes": json.dumps(parsed.get("root_causes", [])),
                "suggested_fixes": json.dumps(parsed.get("suggested_fixes", [])),
                "business_impact": parsed.get("business_impact", ""),
                "raw_response": raw_response,
                "prompt_version": PROMPT_VERSION,
                "confidence": parsed.get("confidence", "low"),
                "provider_name": provider_name,
                "model_name": model_name,
                "token_usage": token_usage,
                "parsing_failure": parsed.get("parsing_failure", False),
            },
        )


async def get_existing_summary(batch_id: int) -> AIEnrichment | None:
    """
    Idempotency check: returns cached AIEnrichment if a summary already
    exists for this batch_id, or None if generation is needed.
    """
    async with db_engine.connect() as conn:
        row = (await conn.execute(
            text("""
                SELECT summary, root_causes, suggested_fixes, business_impact, effective_confidence, prompt_version
                FROM dq_results.llm_summaries
                WHERE violation_batch_id = :batch_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"batch_id": batch_id},
        )).mappings().first()

    if not row:
        return None

    return AIEnrichment(
        ai_summary=row["summary"],
        root_causes=row["root_causes"] or [],
        suggested_fixes=row["suggested_fixes"] or [],
        confidence_score=None,  # We can map confidence string if needed, or update AIEnrichment
    )


async def generate_batch_summary(batch_id: int, force: bool = False) -> AIEnrichment | None:
    """
    Main orchestration entry point called by the Celery worker.
    """
    settings = get_settings()
    if not settings.llm_enabled:
        logger.debug("LLM enrichment disabled (LLM_ENABLED=false). Skipping.")
        return None

    # --- Idempotency check ---
    if not force:
        existing = await get_existing_summary(batch_id)
        if existing:
            logger.info("LLM summary already exists for batch_id=%s. Reusing.", batch_id)
            return existing

    # --- Fetch context ---
    context = await _fetch_batch_context(batch_id)
    if not context:
        logger.warning("Batch %s not found in DB. Cannot generate LLM summary.", batch_id)
        return None

    # --- Build prompt ---
    user_prompt = build_summarization_prompt(
        rule_name=context["rule_name"],
        rule_description=None,
        severity=context["severity"],
        violation_count=context["violation_count"],
        sample_rows=context["sample_rows"],
        trend_summary=context["trend_summary"],
    )

    # --- Call provider ---
    provider = GroqProvider()
    raw_response_str = ""
    t0 = time.monotonic()
    
    raw_dict = {}

    try:
        raw_dict = await provider.generate_json(user_prompt, SYSTEM_PROMPT)
        raw_response_str = json.dumps(raw_dict)
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "LLM call succeeded. batch_id=%s latency_ms=%s",
            batch_id,
            latency_ms,
        )
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error(
            "LLM provider call failed for batch_id=%s latency_ms=%s error=%s",
            batch_id,
            latency_ms,
            exc,
        )
        # If API call fails, we don't persist a parsing_failure, we just let the task retry or fallback.
        # It's better to raise if it's transient so Celery can retry, but worker.py expects None for fallback.
        # Wait, if we return None, worker.py will fallback without retrying.
        # Since we want Celery to retry transient network errors, we SHOULD let the exception bubble up to worker.py.
        raise

    # --- Validate response ---
    parsed = llm_parser.parse_and_validate(raw_dict)
    
    # Re-inject _meta if it got stripped by parse_and_validate
    if "_meta" in raw_dict:
        parsed["_meta"] = raw_dict["_meta"]
        
    if parsed.get("parsing_failure"):
        logger.error(
            "LLM response failed schema validation for batch_id=%s. raw=%s",
            batch_id,
            raw_response_str[:500],
        )

    # --- Phase B: Human-Validated Notification Enrichment ---
    try:
        historical = await _get_historical_human_correction(context["rule_id"])
    except Exception as exc:
        logger.error(
            "Failed to fetch historical human correction for rule_id=%s. error=%s",
            context["rule_id"],
            exc,
        )
        historical = None

    final_summary = parsed["summary"]
    final_fixes = parsed["suggested_fixes"]
    
    if historical:
        # If accepted, use the original summary they accepted. If edited, use the edit.
        h_summary = historical.get("edited_summary") or historical.get("original_summary")
        h_fixes = historical.get("edited_fixes")
        
        if h_summary:
            final_summary = (
                f"Human-validated interpretation:\n{h_summary}\n\n"
                f"Originally AI-generated, corrected by: {historical.get('user_id', 'ops_admin')}\n"
                f"Confidence: High"
            )
            
        if h_fixes:
            try:
                final_fixes = json.loads(h_fixes) if isinstance(h_fixes, str) else h_fixes
            except Exception:
                pass
                
        # Overwrite parsed so it persists to DB with the injected text
        parsed["summary"] = final_summary
        parsed["suggested_fixes"] = final_fixes
        parsed["confidence"] = "High (Human Validated)"

    # --- Persist ---
    try:
        await _persist_summary(batch_id, parsed, raw_response_str)
        logger.info("LLM summary persisted for batch_id=%s.", batch_id)
    except Exception as exc:
        logger.error(
            "Failed to persist LLM summary for batch_id=%s. error=%s",
            batch_id,
            exc,
        )
        pass

    # --- Phase D: Trigger Async Indexing ---
    try:
        from app.services.ai_rules.correlation import index_incident
        import asyncio
        asyncio.create_task(index_incident(batch_id, context["rule_id"], final_summary, context["severity"]))
    except Exception as exc:
        logger.error("Failed to enqueue semantic correlation index for batch_id=%s. error=%s", batch_id, exc)

    return AIEnrichment(
        ai_summary=final_summary,
        root_causes=parsed["root_causes"],
        suggested_fixes=final_fixes,
    )
