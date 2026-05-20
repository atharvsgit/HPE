"""
app/platform/orchestration/flow_controller.py
----------------------------------------------
Central Prefect 3 pipeline orchestration flow.

This is the "brain" of the Platform Intelligence layer. It chains together:
    1. Data profiling      (Polars-based profiling engine)
    2. Validation          (Atharv's saved-rule executor)
    3. Rule suggestion     (heuristic or Gemini + sanitizer)
    4. Anomaly detection   (Isolation Forest / Z-score / LOF)
    5. Storage/logging     (PostgreSQL pipeline metadata and events)

Design choices:
  - PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true lets local/Docker runs execute
    without a separately managed Prefect server.
  - Tasks use async functions compatible with FastAPI's event loop.
  - The flow is triggered via the REST API or the platform task scheduler.
  - Prefect's @flow and @task decorators provide retry logic, structured logging,
    and future observability (connect a Prefect Cloud workspace without code changes).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from prefect import flow, task
from sqlalchemy import text

from app.daemon import executor, registry
from app.db.session import metadata_engine
from app.platform.data_access import validate_table_name
from app.platform.detection.anomaly_detector import (
    AnomalyDetectorError,
    detect_anomalies,
)
from app.platform.logger import get_logger
from app.platform.orchestration.dependency_manager import build_default_pipeline_graph
from app.platform.orchestration.execution_logger import log_pipeline_event
from app.platform.orchestration.retry_handler import (
    DEFAULT_POLICY,
    EXTERNAL_API_POLICY,
    NO_RETRY_POLICY,
    retry_kwargs,
)
from app.platform.profiling.profiler import profile_table
from app.platform.rule_intelligence.heuristic_engine import suggest_rules
from app.platform.rule_intelligence.query_planner import (
    QueryPlannerError,
    extract_table_names,
)
from app.platform.rule_intelligence.sanitizer import sanitize_suggestions
from app.settings import get_settings

log = get_logger(__name__)


# =============================================================================
# Prefect Tasks
# =============================================================================


@task(name="profile-table", **retry_kwargs(DEFAULT_POLICY))
async def profile_table_task(table_name: str) -> dict[str, Any]:
    """Profile the target table and return the profile dict."""
    log.info("[TASK] profile_table_task: '{t}'", t=table_name)
    return await profile_table(table_name)


@task(name="persist-profile", **retry_kwargs(DEFAULT_POLICY))
async def persist_profile_task(
    profile: dict[str, Any], table_name: str, run_id: int
) -> int:
    """Persist the profile dict to dq_platform.dataset_profiles and return profile_id."""
    log.info("[TASK] persist_profile_task for run_id={r}", r=run_id)
    async with metadata_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO dq_platform.dataset_profiles
                    (run_id, table_name, row_count, column_count,
                     null_summary, schema_info, statistics, uniqueness, profiled_at)
                VALUES
                    (:run_id, :table_name, :row_count, :column_count,
                     CAST(:null_summary AS jsonb), CAST(:schema_info AS jsonb),
                     CAST(:statistics AS jsonb), CAST(:uniqueness AS jsonb), :profiled_at)
                RETURNING profile_id
                """
            ),
            {
                "run_id": run_id,
                "table_name": table_name,
                "row_count": profile.get("row_count"),
                "column_count": profile.get("column_count"),
                "null_summary": _to_json(profile.get("null_summary", {})),
                "schema_info": _to_json(profile.get("schema_info", {})),
                "statistics": _to_json(profile.get("statistics", {})),
                "uniqueness": _to_json(profile.get("uniqueness", {})),
                "profiled_at": _profiled_at_value(profile.get("profiled_at")),
            },
        )
        row = result.mappings().one()
    await log_pipeline_event(
        run_id,
        "profiling",
        "Dataset profile persisted.",
        details={"profile_id": row["profile_id"]},
    )
    return row["profile_id"]


@task(name="suggest-rules", **retry_kwargs(EXTERNAL_API_POLICY))
async def suggest_rules_task(
    profile: dict[str, Any], table_name: str, profile_id: int
) -> dict[str, Any]:
    """
    Generate rule suggestions (heuristic or Gemini), sanitize them, and persist them.
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
            raw_suggestions = await suggest_rules_gemini(profile, table_name)
        except GeminiEngineError as exc:
            log.warning("Gemini failed ({e}), falling back to heuristic.", e=exc)
            raw_suggestions = suggest_rules(profile, table_name)
    else:
        raw_suggestions = suggest_rules(profile, table_name)

    suggestions, rejected = sanitize_suggestions(raw_suggestions, table_name)
    for rejection in rejected:
        log.warning(
            "Rejected suggestion '{rule}': {reason}",
            rule=rejection.rule_name,
            reason=rejection.reason,
        )

    await _persist_suggestions(suggestions, profile_id)
    return {
        "suggestions": suggestions,
        "rejected": [r.__dict__ for r in rejected],
    }


@task(name="validate-saved-rules", **retry_kwargs(DEFAULT_POLICY))
async def validate_saved_rules_task(table_name: str, run_id: int) -> dict[str, Any]:
    """Run Atharv's saved validation rules that target the current table."""
    log.info("[TASK] validate_saved_rules_task for '{t}'", t=table_name)
    rules = await registry.list_rules()
    matching_rules = [
        rule
        for rule in rules
        if rule.is_enabled and _rule_targets_table(rule.sql, table_name)
    ]

    summary: dict[str, Any] = {
        "total_rules": len(matching_rules),
        "pass_count": 0,
        "fail_count": 0,
        "error_count": 0,
        "results": [],
    }

    for rule in matching_rules:
        result = await executor.execute_rule(
            registry.execution_request_from_saved_rule(rule)
        )
        match result.status:
            case "PASS":
                summary["pass_count"] += 1
            case "FAIL":
                summary["fail_count"] += 1
            case "ERROR":
                summary["error_count"] += 1

        result_summary = {
            "rule_id": rule.rule_id,
            "rule_name": rule.rule_name,
            "status": result.status,
            "error": result.error.message if result.error else None,
        }
        summary["results"].append(result_summary)
        await log_pipeline_event(
            run_id,
            "validation",
            f"Validation rule {rule.rule_id} finished with {result.status}.",
            level="ERROR" if result.status == "ERROR" else "INFO",
            details=result_summary,
        )

    return summary


@task(name="detect-anomalies-task", **retry_kwargs(DEFAULT_POLICY))
async def detect_anomalies_task(
    table_name: str,
    profile: dict[str, Any],
    run_id: int,
) -> list[dict[str, Any]]:
    """
    Run anomaly detection on all numeric columns found in the profile.
    Persists results and returns a summary list.
    """
    schema_info: dict[str, str] = profile.get("schema_info", {})
    numeric_cols = [
        col
        for col, dtype in schema_info.items()
        if dtype in ("integer", "float", "decimal")
    ]

    log.info(
        "[TASK] detect_anomalies_task: {n} numeric columns in '{t}'.",
        n=len(numeric_cols),
        t=table_name,
    )

    results: list[dict[str, Any]] = []
    for col in numeric_cols:
        try:
            result = await detect_anomalies(
                table_name=table_name,
                column_name=col,
                method="isolation_forest",
            )
            await _persist_anomaly(result, run_id)
            results.append(
                {
                    "column": col,
                    "anomaly_count": result.anomaly_count,
                    "anomaly_pct": result.anomaly_pct,
                }
            )
        except AnomalyDetectorError as exc:
            log.warning("Anomaly detection skipped for col '{c}': {e}", c=col, e=exc)
            await log_pipeline_event(
                run_id,
                "anomaly",
                f"Anomaly detection skipped for column {col}.",
                level="WARNING",
                details={"error": str(exc)},
            )

    return results


@task(name="finalize-run", **retry_kwargs(NO_RETRY_POLICY))
async def finalize_run_task(
    run_id: int,
    status: str,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Update pipeline_runs row with final status, metadata, and finished_at timestamp."""
    log.info("[TASK] finalize_run_task: run_id={r}, status='{s}'", r=run_id, s=status)
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE dq_platform.pipeline_runs
                SET status = :status,
                    finished_at = :finished_at,
                    error = :error,
                    metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:metadata AS jsonb)
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "finished_at": datetime.now(UTC),
                "error": error,
                "metadata": _to_json(metadata or {}),
            },
        )
    await log_pipeline_event(
        run_id,
        "finalize",
        f"Pipeline finalized with status {status}.",
        level="ERROR" if status == "FAILED" else "INFO",
        details={"error": error, "metadata": metadata or {}},
    )


# =============================================================================
# Prefect Flow
# =============================================================================


@flow(
    name="dq-platform-pipeline",
    description=(
        "Full data quality platform pipeline: "
        "profile → validate → suggest → detect → finalize"
    ),
    retries=1,
    retry_delay_seconds=30,
)
async def run_full_pipeline(table_name: str, run_id: int) -> dict[str, Any]:
    """
    Execute the complete Platform Intelligence pipeline for *table_name*.

    Pipeline stages (from dependency graph):
        profile → validate + suggest + anomaly → finalize
    """
    log.info("Pipeline starting for '{t}' (run_id={r})", t=table_name, r=run_id)

    await _update_run_status(run_id, "RUNNING")

    graph = build_default_pipeline_graph()
    execution_order = graph.resolve()
    log.info("Execution order: {order}", order=execution_order)
    await log_pipeline_event(
        run_id,
        "flow",
        "Pipeline started.",
        details={"table_name": table_name, "execution_order": execution_order},
    )

    try:
        # Stage 1: Profile (must succeed — if this fails, the whole pipeline fails).
        profile = await profile_table_task(table_name)
        profile_id = await persist_profile_task(profile, table_name, run_id)

        # Stage 2: validation, suggestion, and anomaly stages can run concurrently.
        suggestions_result, validation_result, anomalies_result = await asyncio.gather(
            suggest_rules_task(profile, table_name, profile_id),
            validate_saved_rules_task(table_name, run_id),
            detect_anomalies_task(table_name, profile, run_id),
            return_exceptions=True,
        )

        stage_errors: list[str] = []
        suggestions_payload = _unwrap_stage_result(
            "suggest",
            suggestions_result,
            stage_errors,
            default={"suggestions": [], "rejected": []},
        )
        validation = _unwrap_stage_result(
            "validation",
            validation_result,
            stage_errors,
            default={
                "total_rules": 0,
                "pass_count": 0,
                "fail_count": 0,
                "error_count": 0,
                "results": [],
            },
        )
        anomalies = _unwrap_stage_result(
            "anomaly",
            anomalies_result,
            stage_errors,
            default=[],
        )

        if validation.get("error_count", 0) > 0:
            stage_errors.append(
                f"validation: {validation['error_count']} rule execution error(s)"
            )

        final_status = "SUCCESS" if not stage_errors else "PARTIAL_SUCCESS"
        metadata = {
            "execution_order": execution_order,
            "profile_id": profile_id,
            "suggestion_count": len(suggestions_payload["suggestions"]),
            "rejected_suggestion_count": len(suggestions_payload["rejected"]),
            "validation": validation,
            "anomaly_column_count": len(anomalies),
            "anomalies": anomalies,
            "stage_warnings": stage_errors,
        }
        await finalize_run_task(
            run_id,
            final_status,
            error="; ".join(stage_errors) if stage_errors else None,
            metadata=metadata,
        )

        result = {
            "run_id": run_id,
            "table_name": table_name,
            **metadata,
            "status": final_status,
        }
        log.info(
            "Pipeline completed for run_id={r}. Status={s}. Warnings: {w}",
            r=run_id,
            s=final_status,
            w=stage_errors,
        )
        return result

    except Exception as exc:
        error_msg = str(exc)
        log.error("Pipeline FAILED for run_id={r}: {e}", r=run_id, e=error_msg)
        await finalize_run_task(run_id, "FAILED", error=error_msg)
        await log_pipeline_event(
            run_id,
            "flow",
            "Pipeline failed.",
            level="ERROR",
            details={"error": error_msg},
        )
        raise


# =============================================================================
# DB helpers
# =============================================================================


async def create_pipeline_run(
    table_name: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    """
    Insert a new PENDING pipeline_run record and return its run_id.
    Called by the API endpoint or platform scheduler before launching the flow.
    """
    validate_table_name(table_name)
    async with metadata_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO dq_platform.pipeline_runs (table_name, status, metadata)
                VALUES (:table_name, 'PENDING', CAST(:metadata AS jsonb))
                RETURNING run_id
                """
            ),
            {"table_name": table_name, "metadata": _to_json(metadata or {})},
        )
        run_id = result.mappings().one()["run_id"]
    await log_pipeline_event(
        run_id,
        "trigger",
        "Pipeline run created.",
        details={"table_name": table_name, "metadata": metadata or {}},
    )
    return run_id


async def _update_run_status(run_id: int, status: str) -> None:
    """Update pipeline_runs status field (used for PENDING → RUNNING transition)."""
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE dq_platform.pipeline_runs
                SET status = :status
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id, "status": status},
        )
    await log_pipeline_event(run_id, "flow", f"Pipeline status changed to {status}.")


async def _persist_suggestions(
    suggestions: list[dict[str, Any]], profile_id: int
) -> None:
    """Bulk-insert sanitized rule suggestions linked to a profile."""
    if not suggestions:
        return
    async with metadata_engine.begin() as conn:
        for suggestion in suggestions:
            await conn.execute(
                text(
                    """
                    INSERT INTO dq_platform.rule_suggestions
                        (profile_id, table_name, column_name, suggestion_type,
                         suggested_rule_name, suggested_sql,
                         expected_result_type, expected_result_value, confidence)
                    VALUES
                        (:profile_id, :table_name, :column_name, :suggestion_type,
                         :suggested_rule_name, :suggested_sql,
                         :expected_result_type, :expected_result_value, :confidence)
                    """
                ),
                {"profile_id": profile_id, **suggestion},
            )


async def _persist_anomaly(result, run_id: int) -> None:
    """Persist a single AnomalyDetectionResult row."""
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO dq_platform.anomaly_results
                    (run_id, table_name, column_name, method,
                     anomaly_count, total_rows, anomaly_pct, details)
                VALUES
                    (:run_id, :table_name, :column_name, :method,
                     :anomaly_count, :total_rows, :anomaly_pct, CAST(:details AS jsonb))
                """
            ),
            {
                "run_id": run_id,
                "table_name": result.table_name,
                "column_name": result.column_name,
                "method": result.method,
                "anomaly_count": result.anomaly_count,
                "total_rows": result.total_rows,
                "anomaly_pct": result.anomaly_pct,
                "details": _to_json(
                    {
                        "anomalous_values": result.anomalous_values,
                        "anomalous_indices": result.anomalous_indices,
                    }
                ),
            },
        )
    await log_pipeline_event(
        run_id,
        "anomaly",
        f"Anomaly result persisted for column {result.column_name}.",
        details={
            "column": result.column_name,
            "method": result.method,
            "anomaly_count": result.anomaly_count,
            "anomaly_pct": result.anomaly_pct,
        },
    )


def _rule_targets_table(sql: str, table_name: str) -> bool:
    try:
        referenced = extract_table_names(sql)
    except QueryPlannerError as exc:
        log.warning(
            "Skipping saved rule with unparsable SQL during pipeline validation: {e}",
            e=exc,
        )
        return False

    target_names = _table_aliases(table_name)
    return any(_normalize_table_name(name) in target_names for name in referenced)


def _table_aliases(table_name: str) -> set[str]:
    normalized = _normalize_table_name(table_name)
    aliases = {normalized}
    if "." in normalized:
        aliases.add(normalized.split(".")[-1])
    return aliases


def _normalize_table_name(table_name: str) -> str:
    return table_name.replace('"', "").lower()


def _unwrap_stage_result(
    stage_name: str,
    result: Any,
    stage_errors: list[str],
    default: Any,
) -> Any:
    if isinstance(result, Exception):
        stage_errors.append(f"{stage_name}: {result}")
        log.error("{stage} stage failed: {e}", stage=stage_name, e=result)
        return default
    return result


def _to_json(obj: Any) -> str:
    return json.dumps(obj, default=str)


def _profiled_at_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return datetime.now(UTC)
