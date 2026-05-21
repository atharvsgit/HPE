"""
app/platform/orchestration/flow_controller.py
----------------------------------------------
Central Prefect 3 pipeline orchestration flow.

This is the "brain" of the Platform Intelligence layer. It chains together:
    1. Data profiling      (Polars-based profiling engine)
    2. Rule suggestion     (heuristic or Gemini)
    3. Anomaly detection   (Isolation Forest / Z-score / LOF)
    4. Persist results     (PostgreSQL via SQLAlchemy)

Design choices:
  - PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true for local Prefect 3 demo runs.
  - Tasks use async functions compatible with FastAPI's event loop.
  - The flow is triggered via the REST API; it runs in a background asyncio task.
  - Prefect's @flow and @task decorators provide retry logic, structured logging,
    and future observability (connect a Prefect Cloud workspace without code changes).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.session import metadata_engine
from app.platform.detection.anomaly_detector import AnomalyDetectorError, detect_anomalies
from app.platform.logger import get_logger
from app.platform.orchestration.dependency_manager import build_default_pipeline_graph
from app.platform.orchestration.retry_handler import (
    DEFAULT_POLICY,
    EXTERNAL_API_POLICY,
    NO_RETRY_POLICY,
    retry_kwargs,
)
from app.platform.profiling.profiler import ProfilerError, profile_table
from app.platform.rule_intelligence.heuristic_engine import suggest_rules
from app.settings import get_settings

log = get_logger(__name__)


try:
    from prefect import flow, task
except ImportError:
    def _local_prefect_decorator(**_kwargs):
        def decorator(func):
            func.fn = func
            return func

        return decorator

    def flow(**kwargs):
        return _local_prefect_decorator(**kwargs)

    def task(**kwargs):
        return _local_prefect_decorator(**kwargs)


# =============================================================================
# Prefect Tasks
# =============================================================================

@task(name="profile-table", **retry_kwargs(DEFAULT_POLICY))
async def profile_table_task(table_name: str) -> dict:
    """Profile the target table and return the profile dict."""
    log.info("[TASK] profile_table_task: '{t}'", t=table_name)
    return await profile_table(table_name)


@task(name="persist-profile", **retry_kwargs(DEFAULT_POLICY))
async def persist_profile_task(profile: dict, table_name: str, run_id: int) -> int:
    """Persist the profile dict to dq_platform.dataset_profiles and return profile_id."""
    log.info("[TASK] persist_profile_task for run_id={r}", r=run_id)
    async with metadata_engine.begin() as conn:
        result = await conn.execute(
            text("""
                INSERT INTO dq_platform.dataset_profiles
                    (run_id, table_name, row_count, column_count,
                     null_summary, schema_info, statistics, uniqueness, profiled_at)
                VALUES
                    (:run_id, :table_name, :row_count, :column_count,
                     CAST(:null_summary AS jsonb), CAST(:schema_info AS jsonb),
                     CAST(:statistics AS jsonb), CAST(:uniqueness AS jsonb), :profiled_at)
                RETURNING profile_id
            """),
            {
                "run_id": run_id,
                "table_name": table_name,
                "row_count": profile.get("row_count"),
                "column_count": profile.get("column_count"),
                "null_summary": _to_json(profile.get("null_summary", {})),
                "schema_info": _to_json(profile.get("schema_info", {})),
                "statistics": _to_json(profile.get("statistics", {})),
                "uniqueness": _to_json(profile.get("uniqueness", {})),
                "profiled_at": _coerce_datetime(profile.get("profiled_at", datetime.now(UTC))),
            },
        )
        row = result.mappings().one()
    return row["profile_id"]


@task(name="suggest-rules", **retry_kwargs(EXTERNAL_API_POLICY))
async def suggest_rules_task(profile: dict, table_name: str, profile_id: int) -> list[dict]:
    """
    Generate rule suggestions (heuristic or Gemini) and persist them.
    Returns the list of suggestion dicts.
    """
    settings = get_settings()
    backend = settings.rule_suggestion_backend
    log.info("[TASK] suggest_rules_task: backend='{b}'", b=backend)

    if backend == "gemini":
        from app.platform.rule_intelligence.gemini_engine import (
            GeminiEngineError,
            suggest_rules_gemini,
        )
        try:
            suggestions = await suggest_rules_gemini(profile, table_name)
        except GeminiEngineError as exc:
            log.warning("Gemini failed ({e}), falling back to heuristic.", e=exc)
            suggestions = suggest_rules(profile, table_name)
    else:
        suggestions = suggest_rules(profile, table_name)

    await _persist_suggestions(suggestions, profile_id)
    return suggestions


@task(name="detect-anomalies-task", **retry_kwargs(DEFAULT_POLICY))
async def detect_anomalies_task(
    table_name: str,
    profile: dict,
    run_id: int,
) -> list[dict]:
    """
    Run anomaly detection on all numeric columns found in the profile.
    Persists results and returns a summary list.
    """
    settings = get_settings()
    schema_info: dict[str, str] = profile.get("schema_info", {})
    numeric_cols = [
        col for col, dtype in schema_info.items()
        if dtype in ("integer", "float", "decimal")
    ]

    log.info(
        "[TASK] detect_anomalies_task: {n} numeric columns in '{t}'.",
        n=len(numeric_cols), t=table_name,
    )

    results: list[dict] = []
    for col in numeric_cols:
        try:
            result = await detect_anomalies(
                table_name=table_name,
                column_name=col,
                method="isolation_forest",
            )
            await _persist_anomaly(result, run_id)
            results.append({
                "column": col,
                "anomaly_count": result.anomaly_count,
                "anomaly_pct": result.anomaly_pct,
            })
        except AnomalyDetectorError as exc:
            log.warning("Anomaly detection skipped for col '{c}': {e}", c=col, e=exc)

    return results


@task(name="finalize-run", **retry_kwargs(NO_RETRY_POLICY))
async def finalize_run_task(run_id: int, status: str, error: str | None = None) -> None:
    """Update pipeline_runs row with final status and finished_at timestamp."""
    log.info("[TASK] finalize_run_task: run_id={r}, status='{s}'", r=run_id, s=status)
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text("""
                UPDATE dq_platform.pipeline_runs
                SET status = :status,
                    finished_at = :finished_at,
                    error = :error
                WHERE run_id = :run_id
            """),
            {
                "run_id": run_id,
                "status": status,
                "finished_at": datetime.now(UTC),
                "error": error,
            },
        )


# =============================================================================
# Prefect Flow
# =============================================================================

@flow(
    name="dq-platform-pipeline",
    description="Full data quality platform pipeline: profile → suggest → detect → finalize",
    retries=1,
    retry_delay_seconds=30,
)
async def run_full_pipeline(table_name: str, run_id: int) -> dict[str, Any]:
    """
    Execute the complete Platform Intelligence pipeline for *table_name*.

    Pipeline stages (from dependency graph):
        profile  → suggest + anomaly  → finalize

    Args:
        table_name: Fully-qualified PostgreSQL table (e.g. ``business_data.employees``).
        run_id:     Primary key of the pre-created pipeline_runs row.

    Returns:
        A summary dict with profile, suggestions, and anomaly results.
    """
    log.info("Pipeline starting for '{t}' (run_id={r})", t=table_name, r=run_id)

    # Fix (Copilot): Mark the run as RUNNING immediately so status polling shows progress
    await _update_run_status(run_id, "RUNNING")

    # Log dependency graph for observability
    graph = build_default_pipeline_graph()
    execution_order = graph.resolve()
    log.info("Execution order: {order}", order=execution_order)

    try:
        # Stage 1: Profile (must succeed — if this fails, the whole pipeline fails)
        profile = await profile_table_task(table_name)
        profile_id = await persist_profile_task(profile, table_name, run_id)

        # Stage 2: Suggest + Anomaly run concurrently; partial failure is tolerated
        suggestions_result, anomalies_result = await asyncio.gather(
            suggest_rules_task(profile, table_name, profile_id),
            detect_anomalies_task(table_name, profile, run_id),
            return_exceptions=True,
        )

        # Fix (Copilot): Explicitly distinguish exceptions from real results
        # Log partial failures and record them in metadata, but don't silently succeed.
        stage_errors: list[str] = []

        if isinstance(suggestions_result, Exception):
            stage_errors.append(f"suggest: {suggestions_result}")
            log.error("Suggestion stage failed: {e}", e=suggestions_result)
            suggestions: list = []
        else:
            suggestions = suggestions_result

        if isinstance(anomalies_result, Exception):
            stage_errors.append(f"anomaly: {anomalies_result}")
            log.error("Anomaly detection stage failed: {e}", e=anomalies_result)
            anomalies: list = []
        else:
            anomalies = anomalies_result

        # Stage 3: Finalize. The current schema supports SUCCESS/FAILED, so
        # non-critical stage failures are recorded in the run error field.
        final_status = "SUCCESS"
        await finalize_run_task(
            run_id,
            final_status,
            error="; ".join(stage_errors) if stage_errors else None,
        )

        result = {
            "run_id": run_id,
            "table_name": table_name,
            "profile_id": profile_id,
            "suggestion_count": len(suggestions),
            "anomaly_column_count": len(anomalies),
            "anomalies": anomalies,
            "stage_warnings": stage_errors,
        }
        log.info("Pipeline completed for run_id={r}. Warnings: {w}", r=run_id, w=stage_errors)
        return result

    except (ProfilerError, Exception) as exc:
        error_msg = str(exc)
        log.error("Pipeline FAILED for run_id={r}: {e}", r=run_id, e=error_msg)
        await finalize_run_task(run_id, "FAILED", error=error_msg)
        raise


# =============================================================================
# DB helpers
# =============================================================================

async def create_pipeline_run(table_name: str) -> int:
    """
    Insert a new PENDING pipeline_run record and return its run_id.
    Called by the API endpoint before launching the flow background task.
    """
    async with metadata_engine.begin() as conn:
        result = await conn.execute(
            text("""
                INSERT INTO dq_platform.pipeline_runs (table_name, status)
                VALUES (:table_name, 'PENDING')
                RETURNING run_id
            """),
            {"table_name": table_name},
        )
        return result.mappings().one()["run_id"]


async def _update_run_status(run_id: int, status: str) -> None:
    """Update pipeline_runs status field (used for PENDING → RUNNING transition)."""
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text("""
                UPDATE dq_platform.pipeline_runs
                SET status = :status
                WHERE run_id = :run_id
            """),
            {"run_id": run_id, "status": status},
        )


async def _persist_suggestions(suggestions: list[dict], profile_id: int) -> None:
    """Bulk-insert rule suggestions linked to a profile."""
    if not suggestions:
        return
    async with metadata_engine.begin() as conn:
        for s in suggestions:
            await conn.execute(
                text("""
                    INSERT INTO dq_platform.rule_suggestions
                        (profile_id, table_name, column_name, suggestion_type,
                         suggested_rule_name, suggested_sql,
                         expected_result_type, expected_result_value, confidence)
                    VALUES
                        (:profile_id, :table_name, :column_name, :suggestion_type,
                         :suggested_rule_name, :suggested_sql,
                         :expected_result_type, :expected_result_value, :confidence)
                """),
                {
                    "profile_id": profile_id,
                    **{k: s.get(k) for k in (
                        "table_name", "column_name", "suggestion_type",
                        "suggested_rule_name", "suggested_sql",
                        "expected_result_type", "expected_result_value", "confidence",
                    )},
                },
            )


async def _persist_anomaly(result, run_id: int) -> None:
    """Persist a single AnomalyDetectionResult row."""
    import json
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO dq_platform.anomaly_results
                    (run_id, table_name, column_name, method,
                     anomaly_count, total_rows, anomaly_pct, details)
                VALUES
                    (:run_id, :table_name, :column_name, :method,
                     :anomaly_count, :total_rows, :anomaly_pct, CAST(:details AS jsonb))
            """),
            {
                "run_id": run_id,
                "table_name": result.table_name,
                "column_name": result.column_name,
                "method": result.method,
                "anomaly_count": result.anomaly_count,
                "total_rows": result.total_rows,
                "anomaly_pct": result.anomaly_pct,
                "details": json.dumps({
                    "anomalous_values": result.anomalous_values,
                    "anomalous_indices": result.anomalous_indices,
                }),
            },
        )


def _to_json(obj: Any) -> str:
    import json
    return json.dumps(obj, default=str)


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
