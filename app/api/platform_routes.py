"""
app/api/platform_routes.py
----------------------------
FastAPI router for all Platform Intelligence endpoints.

All endpoints are grouped under the ``/platform`` prefix.
The router is registered in ``app/main.py`` alongside Atharv's ``/rules`` router.

Endpoints:
    POST /platform/pipeline/trigger          — start a full pipeline run
    GET  /platform/pipeline/runs             — list all pipeline runs
    GET  /platform/pipeline/runs/{run_id}    — get one run's status
    POST /platform/profile                   — profile a table
    GET  /platform/profile/{table_name}      — get latest profile for a table
    POST /platform/suggestions               — generate rule suggestions
    GET  /platform/suggestions               — list all rule suggestions
    POST /platform/suggestions/{id}/apply    — apply a suggestion as a saved rule
    POST /platform/anomaly/detect            — run anomaly detection
    GET  /platform/anomaly/results           — list anomaly results
    POST /platform/drift/detect              — run drift detection
    GET  /platform/drift/results             — list drift results
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import text

from app.daemon.cron import CronValidationError
from app.daemon.registry import DuplicateRuleError, create_rule
from app.daemon.sql_safety import SQLSafetyError
from app.db.session import metadata_engine
from app.models.platform_requests import (
    AnomalyDetectionRequest,
    ApplySuggestionRequest,
    DriftDetectionRequest,
    PipelineTriggerRequest,
    ProfileRequest,
    RuleSuggestionRequest,
)
from app.models.platform_responses import (
    AnomalyResultResponse,
    ColumnDriftResultResponse,
    DatasetProfileResponse,
    DriftResultResponse,
    PipelineRunResponse,
    PipelineTriggerResponse,
    RuleSuggestionResponse,
)
from app.models.requests import ExpectedResult, SavedRuleCreateRequest
from app.platform.detection.anomaly_detector import AnomalyDetectorError, detect_anomalies
from app.platform.detection.drift_detector import DriftDetectorError, detect_drift
from app.platform.logger import get_logger
from app.platform.orchestration.flow_controller import (
    create_pipeline_run,
    run_full_pipeline,
)
from app.platform.profiling.profiler import ProfilerError, profile_table
from app.platform.rule_intelligence.gemini_engine import (
    GeminiEngineError,
    suggest_rules_gemini,
)
from app.platform.rule_intelligence.heuristic_engine import suggest_rules
from app.platform.rule_intelligence.query_planner import (
    QueryPlannerError,
    validate_and_optimize,
)

log = get_logger(__name__)
platform_router = APIRouter(prefix="/platform", tags=["Platform Intelligence"])


# =============================================================================
# Pipeline orchestration
# =============================================================================

@platform_router.post(
    "/pipeline/trigger",
    response_model=PipelineTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a full platform pipeline run",
)
async def trigger_pipeline(
    request: PipelineTriggerRequest,
    background_tasks: BackgroundTasks,
) -> PipelineTriggerResponse:
    """
    Trigger the full Platform Intelligence pipeline asynchronously.

    The endpoint returns immediately with a ``run_id``. The pipeline runs
    in the background. Poll ``GET /platform/pipeline/runs/{run_id}`` to
    check status.
    """
    run_id = await create_pipeline_run(request.table_name)
    log.info("Pipeline triggered: run_id={r}, table='{t}'", r=run_id, t=request.table_name)

    # Run the Prefect flow in a background asyncio task
    background_tasks.add_task(_run_pipeline_background, request.table_name, run_id)

    return PipelineTriggerResponse(
        run_id=run_id,
        table_name=request.table_name,
        status="PENDING",
    )


async def _run_pipeline_background(table_name: str, run_id: int) -> None:
    """Background wrapper for the Prefect flow."""
    try:
        await run_full_pipeline(table_name=table_name, run_id=run_id)
    except Exception as exc:
        log.error("Background pipeline run_id={r} raised: {e}", r=run_id, e=exc)


@platform_router.get(
    "/pipeline/runs",
    response_model=list[PipelineRunResponse],
    summary="List all pipeline runs",
)
async def list_pipeline_runs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[PipelineRunResponse]:
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT run_id, table_name, status, triggered_at, finished_at, error, metadata
                FROM dq_platform.pipeline_runs
                ORDER BY run_id DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        return [_pipeline_run_from_row(r) for r in result.mappings().all()]


@platform_router.get(
    "/pipeline/runs/{run_id}",
    response_model=PipelineRunResponse,
    summary="Get one pipeline run by ID",
)
async def get_pipeline_run(run_id: int) -> PipelineRunResponse:
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT run_id, table_name, status, triggered_at, finished_at, error, metadata
                FROM dq_platform.pipeline_runs WHERE run_id = :run_id
            """),
            {"run_id": run_id},
        )
        row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Pipeline run not found.")
    return _pipeline_run_from_row(row)


# =============================================================================
# Data profiling
# =============================================================================

@platform_router.post(
    "/profile",
    response_model=DatasetProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Profile a table and persist the result",
)
async def profile_dataset(request: ProfileRequest) -> DatasetProfileResponse:
    """
    Profile *table_name*, persist the result to ``dq_platform.dataset_profiles``,
    and return the full profile.
    """
    try:
        # Fix (Copilot): pass request.row_limit so per-request override actually works
        profile = await profile_table(request.table_name, row_limit=request.row_limit)
    except ProfilerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    profiled_at = _coerce_datetime(profile["profiled_at"])
    async with metadata_engine.begin() as conn:
        result = await conn.execute(
            text("""
                INSERT INTO dq_platform.dataset_profiles
                    (table_name, row_count, column_count,
                     null_summary, schema_info, statistics, uniqueness, profiled_at)
                VALUES
                    (:table_name, :row_count, :column_count,
                     CAST(:null_summary AS jsonb), CAST(:schema_info AS jsonb),
                     CAST(:statistics AS jsonb), CAST(:uniqueness AS jsonb), :profiled_at)
                RETURNING profile_id, profiled_at
            """),
            {
                "table_name": request.table_name,
                "row_count": profile["row_count"],
                "column_count": profile["column_count"],
                "null_summary": json.dumps(profile["null_summary"]),
                "schema_info": json.dumps(profile["schema_info"]),
                "statistics": json.dumps(profile["statistics"], default=str),
                "uniqueness": json.dumps(profile["uniqueness"], default=str),
                "profiled_at": profiled_at,
            },
        )
        row = result.mappings().one()

    return DatasetProfileResponse(
        profile_id=row["profile_id"],
        table_name=request.table_name,
        row_count=profile["row_count"],
        column_count=profile["column_count"],
        null_summary=profile["null_summary"],
        schema_info=profile["schema_info"],
        statistics=profile["statistics"],
        uniqueness=profile["uniqueness"],
        profiled_at=row["profiled_at"],
    )


@platform_router.get(
    "/profile/{table_name}",
    response_model=DatasetProfileResponse,
    summary="Get the latest profile for a table",
)
async def get_latest_profile(table_name: str) -> DatasetProfileResponse:
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT profile_id, run_id, table_name, row_count, column_count,
                       null_summary, schema_info, statistics, uniqueness, profiled_at
                FROM dq_platform.dataset_profiles
                WHERE table_name = :table_name
                ORDER BY profiled_at DESC
                LIMIT 1
            """),
            {"table_name": table_name},
        )
        row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No profile found for '{table_name}'.")
    return _profile_from_row(row)


# =============================================================================
# Rule suggestions
# =============================================================================

@platform_router.post(
    "/suggestions",
    response_model=list[RuleSuggestionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate and persist rule suggestions for a table",
)
async def generate_suggestions(request: RuleSuggestionRequest) -> list[RuleSuggestionResponse]:
    """
    Profile *table_name*, generate rule suggestions using the chosen backend,
    persist them to ``dq_platform.rule_suggestions``, and return all suggestions.

    Set ``backend="gemini"`` to use Gemini 2.5 Flash (requires ``GEMINI_API_KEY``).
    Set ``backend="heuristic"`` (default) for offline rule generation.
    """
    try:
        profile = await profile_table(request.table_name)
    except ProfilerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if request.backend == "gemini":
        try:
            suggestions = await suggest_rules_gemini(profile, request.table_name)
        except GeminiEngineError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Gemini API error: {exc}. Use backend='heuristic' as fallback.",
            ) from exc
    else:
        suggestions = suggest_rules(profile, request.table_name)

    # Fix (Copilot): validation is mandatory; only pretty-print/transpile is best-effort.
    # Suggestions that fail SQL contract validation (wrong column name, non-SELECT, etc.)
    # are SKIPPED and logged rather than persisted with bad SQL.
    validated_suggestions: list[dict] = []
    for s in suggestions:
        try:
            s["suggested_sql"] = validate_and_optimize(s["suggested_sql"])
            validated_suggestions.append(s)
        except QueryPlannerError as exc:
            log.warning(
                "Skipping suggestion '{}' for '{}' — invalid SQL: {}",
                s.get("suggested_rule_name", "?"),
                request.table_name,
                exc,
            )
            # Don't append — contract-violating SQL must not be stored

    # Persist and return
    return await _persist_and_fetch_suggestions(validated_suggestions)


@platform_router.get(
    "/suggestions",
    response_model=list[RuleSuggestionResponse],
    summary="List all rule suggestions",
)
async def list_suggestions(
    table_name: str | None = Query(default=None),
    applied: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[RuleSuggestionResponse]:
    conditions = ["TRUE"]
    params: dict[str, Any] = {"limit": limit}
    if table_name:
        conditions.append("table_name = :table_name")
        params["table_name"] = table_name
    if applied is not None:
        conditions.append("applied = :applied")
        params["applied"] = applied

    where = " AND ".join(conditions)
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text(f"""
                SELECT suggestion_id, profile_id, table_name, column_name,
                       suggestion_type, suggested_rule_name, suggested_sql,
                       expected_result_type, expected_result_value, confidence,
                       applied, applied_rule_id, created_at
                FROM dq_platform.rule_suggestions
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),  # noqa: S608
            params,
        )
        return [_suggestion_from_row(r) for r in result.mappings().all()]


@platform_router.post(
    "/suggestions/{suggestion_id}/apply",
    response_model=RuleSuggestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply a suggestion as a saved validation rule",
)
async def apply_suggestion(
    suggestion_id: int,
    request: ApplySuggestionRequest,
) -> RuleSuggestionResponse:
    """
    Promote a rule suggestion to a saved rule in ``dq_config.dq_rules``.

    The suggestion's SQL is passed through Atharv's safety validator and
    cron validator before saving.
    """
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT * FROM dq_platform.rule_suggestions WHERE suggestion_id = :id"),
            {"id": suggestion_id},
        )
        row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    if row["applied"]:
        raise HTTPException(status_code=409, detail="Suggestion has already been applied.")

    create_request = SavedRuleCreateRequest(
        rule_name=row["suggested_rule_name"],
        sql=row["suggested_sql"],
        expected_result=ExpectedResult(
            type=row["expected_result_type"],
            value=row["expected_result_value"],
        ),
        schedule_cron=request.schedule_cron,
        is_enabled=request.is_enabled,
    )

    try:
        saved_rule = await create_rule(create_request)
    except DuplicateRuleError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "type": "DUPLICATE_RULE",
                "message": str(exc),
                "existing_rule_id": exc.existing_rule_id,
            },
        ) from exc
    except (CronValidationError, SQLSafetyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Mark suggestion as applied
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text("""
                UPDATE dq_platform.rule_suggestions
                SET applied = TRUE, applied_rule_id = :rule_id
                WHERE suggestion_id = :suggestion_id
            """),
            {"rule_id": saved_rule.rule_id, "suggestion_id": suggestion_id},
        )

    # Fetch updated suggestion
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT * FROM dq_platform.rule_suggestions WHERE suggestion_id = :id"),
            {"id": suggestion_id},
        )
        updated = result.mappings().first()
    return _suggestion_from_row(updated)


# =============================================================================
# Anomaly detection
# =============================================================================

@platform_router.post(
    "/anomaly/detect",
    response_model=list[AnomalyResultResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Run anomaly detection on one or more numeric columns",
)
async def run_anomaly_detection(request: AnomalyDetectionRequest) -> list[AnomalyResultResponse]:
    """
    Detect anomalies in the specified columns of *table_name*.

    Supported methods: ``isolation_forest``, ``zscore``, ``lof``.
    """
    results: list[AnomalyResultResponse] = []
    errors: list[str] = []

    for col in request.columns:
        try:
            result = await detect_anomalies(request.table_name, col, request.method)
            persisted = await _persist_anomaly_result(result)
            results.append(persisted)
        except AnomalyDetectorError as exc:
            errors.append(f"{col}: {exc}")

    if errors and not results:
        raise HTTPException(
            status_code=400,
            detail={"message": "All columns failed anomaly detection.", "errors": errors},
        )

    return results


@platform_router.get(
    "/anomaly/results",
    response_model=list[AnomalyResultResponse],
    summary="List anomaly detection results",
)
async def list_anomaly_results(
    table_name: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[AnomalyResultResponse]:
    conditions = ["TRUE"]
    params: dict[str, Any] = {"limit": limit}
    if table_name:
        conditions.append("table_name = :table_name")
        params["table_name"] = table_name

    where = " AND ".join(conditions)
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text(f"""
                SELECT anomaly_id, run_id, table_name, column_name, method,
                       anomaly_count, total_rows, anomaly_pct, details, detected_at
                FROM dq_platform.anomaly_results
                WHERE {where}
                ORDER BY detected_at DESC
                LIMIT :limit
            """),  # noqa: S608
            params,
        )
        return [_anomaly_from_row(r) for r in result.mappings().all()]


# =============================================================================
# Drift detection
# =============================================================================

@platform_router.post(
    "/drift/detect",
    response_model=DriftResultResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run data drift detection between two tables",
)
async def run_drift_detection(request: DriftDetectionRequest) -> DriftResultResponse:
    """
    Compare *reference_table* against *current_table* for drift in *columns*.

    Uses the current lightweight numeric mean-shift drift detector.
    """
    try:
        drift_result = await detect_drift(
            reference_table=request.reference_table,
            current_table=request.current_table,
            columns=request.columns,
        )
    except DriftDetectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    detected_at = datetime.now(UTC)
    await _persist_drift_results(drift_result, detected_at)

    return DriftResultResponse(
        reference_table=drift_result.reference_table,
        current_table=drift_result.current_table,
        columns=drift_result.columns,
        column_results=[
            ColumnDriftResultResponse(
                column_name=r.column_name,
                stat_test=r.stat_test,
                drift_score=r.drift_score,
                is_drifted=r.is_drifted,
            )
            for r in drift_result.column_results
        ],
        dataset_drift_detected=drift_result.dataset_drift_detected,
        share_drifted_columns=drift_result.share_drifted_columns,
        detected_at=detected_at,
    )


@platform_router.get(
    "/drift/results",
    response_model=list[dict],
    summary="List drift detection results",
)
async def list_drift_results(
    reference_table: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    conditions = ["TRUE"]
    params: dict[str, Any] = {"limit": limit}
    if reference_table:
        conditions.append("reference_table = :reference_table")
        params["reference_table"] = reference_table

    where = " AND ".join(conditions)
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text(f"""
                SELECT drift_id, run_id, reference_table, current_table, column_name,
                       stat_test, drift_score, is_drifted, detected_at
                FROM dq_platform.drift_results
                WHERE {where}
                ORDER BY detected_at DESC
                LIMIT :limit
            """),  # noqa: S608
            params,
        )
        return [dict(r) for r in result.mappings().all()]


# =============================================================================
# Internal DB persistence helpers
# =============================================================================

async def _persist_and_fetch_suggestions(suggestions: list[dict]) -> list[RuleSuggestionResponse]:
    """Insert suggestions and return them with generated suggestion_ids."""
    responses: list[RuleSuggestionResponse] = []
    async with metadata_engine.begin() as conn:
        for s in suggestions:
            result = await conn.execute(
                text("""
                    INSERT INTO dq_platform.rule_suggestions
                        (table_name, column_name, suggestion_type, suggested_rule_name,
                         suggested_sql, expected_result_type, expected_result_value, confidence)
                    VALUES
                        (:table_name, :column_name, :suggestion_type, :suggested_rule_name,
                         :suggested_sql, :expected_result_type, :expected_result_value, :confidence)
                    RETURNING suggestion_id, created_at
                """),
                {
                    "table_name": s["table_name"],
                    "column_name": s["column_name"],
                    "suggestion_type": s["suggestion_type"],
                    "suggested_rule_name": s["suggested_rule_name"],
                    "suggested_sql": s["suggested_sql"],
                    "expected_result_type": s["expected_result_type"],
                    "expected_result_value": s.get("expected_result_value"),
                    "confidence": s.get("confidence", 0.5),
                },
            )
            row = result.mappings().one()
            responses.append(RuleSuggestionResponse(
                suggestion_id=row["suggestion_id"],
                table_name=s["table_name"],
                column_name=s["column_name"],
                suggestion_type=s["suggestion_type"],
                suggested_rule_name=s["suggested_rule_name"],
                suggested_sql=s["suggested_sql"],
                expected_result_type=s["expected_result_type"],
                expected_result_value=s.get("expected_result_value"),
                confidence=s.get("confidence", 0.5),
                applied=False,
                created_at=row["created_at"],
            ))
    return responses


async def _persist_anomaly_result(result) -> AnomalyResultResponse:
    """Persist a single anomaly result and return the response model."""
    async with metadata_engine.begin() as conn:
        db_result = await conn.execute(
            text("""
                INSERT INTO dq_platform.anomaly_results
                    (table_name, column_name, method, anomaly_count,
                     total_rows, anomaly_pct, details)
                VALUES
                    (:table_name, :column_name, :method, :anomaly_count,
                     :total_rows, :anomaly_pct, CAST(:details AS jsonb))
                RETURNING anomaly_id, detected_at
            """),
            {
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
        row = db_result.mappings().one()

    return AnomalyResultResponse(
        anomaly_id=row["anomaly_id"],
        table_name=result.table_name,
        column_name=result.column_name,
        method=result.method,
        anomaly_count=result.anomaly_count,
        total_rows=result.total_rows,
        anomaly_pct=result.anomaly_pct,
        details={
            "anomalous_values": result.anomalous_values,
            "anomalous_indices": result.anomalous_indices,
        },
        detected_at=row["detected_at"],
    )


async def _persist_drift_results(drift_result, detected_at: datetime) -> None:
    """Persist all per-column drift results to the DB."""
    async with metadata_engine.begin() as conn:
        for col_result in drift_result.column_results:
            await conn.execute(
                text("""
                    INSERT INTO dq_platform.drift_results
                        (reference_table, current_table, column_name,
                         stat_test, drift_score, is_drifted, detected_at)
                    VALUES
                        (:reference_table, :current_table, :column_name,
                         :stat_test, :drift_score, :is_drifted, :detected_at)
                """),
                {
                    "reference_table": drift_result.reference_table,
                    "current_table": drift_result.current_table,
                    "column_name": col_result.column_name,
                    "stat_test": col_result.stat_test,
                    "drift_score": col_result.drift_score,
                    "is_drifted": col_result.is_drifted,
                    "detected_at": detected_at,
                },
            )


# =============================================================================
# Row → response model converters
# =============================================================================

def _pipeline_run_from_row(row) -> PipelineRunResponse:
    return PipelineRunResponse(
        run_id=row["run_id"],
        table_name=row["table_name"],
        status=row["status"],
        triggered_at=row["triggered_at"],
        finished_at=row.get("finished_at"),
        error=row.get("error"),
        metadata=row.get("metadata"),
    )


def _profile_from_row(row) -> DatasetProfileResponse:
    def _parse(v):
        if isinstance(v, str):
            return json.loads(v)
        return v or {}

    return DatasetProfileResponse(
        profile_id=row["profile_id"],
        run_id=row.get("run_id"),
        table_name=row["table_name"],
        row_count=row["row_count"],
        column_count=row["column_count"],
        null_summary=_parse(row["null_summary"]),
        schema_info=_parse(row["schema_info"]),
        statistics=_parse(row["statistics"]),
        uniqueness=_parse(row["uniqueness"]),
        profiled_at=row["profiled_at"],
    )


def _suggestion_from_row(row) -> RuleSuggestionResponse:
    return RuleSuggestionResponse(
        suggestion_id=row["suggestion_id"],
        profile_id=row.get("profile_id"),
        table_name=row["table_name"],
        column_name=row["column_name"],
        suggestion_type=row["suggestion_type"],
        suggested_rule_name=row["suggested_rule_name"],
        suggested_sql=row["suggested_sql"],
        expected_result_type=row["expected_result_type"],
        expected_result_value=float(row["expected_result_value"]) if row.get("expected_result_value") is not None else None,
        confidence=float(row["confidence"]) if row.get("confidence") is not None else 0.5,
        applied=row["applied"],
        applied_rule_id=row.get("applied_rule_id"),
        created_at=row["created_at"],
    )


def _anomaly_from_row(row) -> AnomalyResultResponse:
    def _parse(v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    return AnomalyResultResponse(
        anomaly_id=row["anomaly_id"],
        run_id=row.get("run_id"),
        table_name=row["table_name"],
        column_name=row["column_name"],
        method=row["method"],
        anomaly_count=row["anomaly_count"],
        total_rows=row["total_rows"],
        anomaly_pct=float(row["anomaly_pct"]),
        details=_parse(row.get("details")),
        detected_at=row["detected_at"],
    )


def _coerce_datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)
