from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import text

from app.daemon import connection, executor, registry
from app.daemon.cron import CronValidationError
from app.daemon.sql_safety import SQLSafetyError
from app.db.session import metadata_engine as db_engine
from app.models.requests import DatabaseConnectionRequest, RuleExecutionRequest, SavedRuleCreateRequest
from app.models.responses import (
    DatabaseConnectionResponse,
    RuleExecutionResult,
    SavedRuleExecutionResultResponse,
    SavedRuleResponse,
    SchedulerRuleStatusResponse,
)
from app.models.violations import ViolationBatch, ViolationEvent
from app.models.feedback import FeedbackCreate, FeedbackResponse

router = APIRouter()


@router.post("/connect-database", response_model=DatabaseConnectionResponse)
async def connect_database(request: DatabaseConnectionRequest) -> DatabaseConnectionResponse:
    try:
        return await connection.connect_database(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "INVALID_DATABASE_CONNECTION", "message": str(exc)},
        ) from exc


@router.post("/rules/run", response_model=RuleExecutionResult)
async def run_rule(rule: RuleExecutionRequest) -> RuleExecutionResult:
    return await executor.execute_rule(rule)


@router.post("/rules", response_model=SavedRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(rule: SavedRuleCreateRequest) -> SavedRuleResponse:
    try:
        return await registry.create_rule(rule)
    except registry.DuplicateRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "DUPLICATE_RULE",
                "message": str(exc),
                "existing_rule_id": exc.existing_rule_id,
            },
        ) from exc
    except (CronValidationError, SQLSafetyError) as exc:
        error_type = "INVALID_CRON" if isinstance(exc, CronValidationError) else exc.code
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": error_type, "message": str(exc)},
        ) from exc


@router.get("/rules", response_model=list[SavedRuleResponse])
async def list_rules() -> list[SavedRuleResponse]:
    return await registry.list_rules()


@router.get("/rules/{rule_id}", response_model=SavedRuleResponse)
async def get_rule(rule_id: int) -> SavedRuleResponse:
    rule = await registry.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int) -> Response:
    deleted = await registry.delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/rules/{rule_id}/run", response_model=RuleExecutionResult)
async def run_saved_rule(rule_id: int) -> RuleExecutionResult:
    saved_rule = await registry.get_rule(rule_id)
    if saved_rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")

    return await executor.execute_rule(registry.execution_request_from_saved_rule(saved_rule))


@router.get("/rules/{rule_id}/results", response_model=list[SavedRuleExecutionResultResponse])
async def list_saved_rule_results(
    rule_id: int,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SavedRuleExecutionResultResponse]:
    saved_rule = await registry.get_rule(rule_id)
    if saved_rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return await registry.list_rule_results(rule_id, limit)


@router.get("/results", response_model=list[SavedRuleExecutionResultResponse])
async def list_all_results(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SavedRuleExecutionResultResponse]:
    return await registry.list_all_results(limit)


@router.get("/scheduler/rules", response_model=list[SchedulerRuleStatusResponse])
async def list_scheduler_rules() -> list[SchedulerRuleStatusResponse]:
    return await registry.list_scheduler_rule_statuses()


# ---------------------------------------------------------------------------
# Intelligent Violation Aggregation Layer – extension endpoints
# ---------------------------------------------------------------------------

@router.get("/violations", response_model=list[ViolationEvent])
async def list_violations(
    limit: int = Query(default=50, ge=1, le=200),
    status: str = Query(default=None),
) -> list[ViolationEvent]:
    async with db_engine.connect() as conn:
        query = """
            SELECT id, rule_id, rule_id AS rule_result_id, severity,
                   violation_count, sample_rows, fingerprint, status, created_at
            FROM dq_results.violation_events
        """
        params: dict = {"limit": limit}
        if status:
            query += " WHERE status = :status"
            params["status"] = status
        query += " ORDER BY created_at DESC LIMIT :limit"
        result = await conn.execute(text(query), params)
        rows = result.mappings().all()
    return [ViolationEvent(**dict(r)) for r in rows]


@router.get("/violations/{violation_id}", response_model=ViolationEvent)
async def get_violation(violation_id: int) -> ViolationEvent:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT id, rule_id, rule_id AS rule_result_id, severity,
                       violation_count, sample_rows, fingerprint, status, created_at
                FROM dq_results.violation_events
                WHERE id = :id
                """
            ),
            {"id": violation_id},
        )
        row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Violation not found.")
    return ViolationEvent(**dict(row))


@router.get("/violation-batches", response_model=list[ViolationBatch])
async def list_violation_batches(
    limit: int = Query(default=50, ge=1, le=200),
    batch_status: str = Query(default=None, alias="status"),
) -> list[ViolationBatch]:
    async with db_engine.connect() as conn:
        query = """
            SELECT vb.id, vb.rule_id, vb.severity, vb.first_seen, vb.last_seen,
                   vb.total_occurrences, vb.total_violation_count, vb.status,
                   ls.summary AS ai_summary, ls.root_causes, ls.suggested_fixes, ls.business_impact,
                   ls.effective_confidence AS confidence_score, ls.prompt_version, ls.provider_name,
                   ls.model_name, ls.token_usage, ls.parsing_failure
            FROM dq_results.violation_batches vb
            LEFT JOIN LATERAL (
                SELECT summary, root_causes, suggested_fixes, business_impact,
                       effective_confidence, prompt_version, provider_name, model_name,
                       token_usage, parsing_failure
                FROM dq_results.llm_summaries
                WHERE violation_batch_id = vb.id
                ORDER BY created_at DESC LIMIT 1
            ) ls ON true
        """
        params: dict = {"limit": limit}
        if batch_status:
            query += " WHERE vb.status = :status"
            params["status"] = batch_status
        query += " ORDER BY vb.last_seen DESC LIMIT :limit"
        result = await conn.execute(text(query), params)
        rows = result.mappings().all()
        
    batches = []
    for r in rows:
        d = dict(r)
        if d.get("ai_summary") or d.get("parsing_failure"):
            d["ai_enrichment"] = {
                "ai_summary": d.pop("ai_summary", None),
                "root_causes": d.pop("root_causes", []),
                "suggested_fixes": d.pop("suggested_fixes", []),
                "confidence_score": d.pop("confidence_score", None),
                "prompt_version": d.pop("prompt_version", None),
                "provider_name": d.pop("provider_name", None),
                "model_name": d.pop("model_name", None),
                "token_usage": d.pop("token_usage", None),
                "parsing_failure": d.pop("parsing_failure", False),
            }
            d.pop("business_impact", None)
        else:
            d.pop("ai_summary", None)
            d.pop("root_causes", None)
            d.pop("suggested_fixes", None)
            d.pop("business_impact", None)
            d.pop("confidence_score", None)
            d.pop("prompt_version", None)
            d.pop("provider_name", None)
            d.pop("model_name", None)
            d.pop("token_usage", None)
            d.pop("parsing_failure", None)
            d["ai_enrichment"] = None
        batches.append(ViolationBatch(**d))
    return batches


@router.post("/violation-batches/{batch_id}/send-now", status_code=status.HTTP_200_OK)
async def force_send_batch(batch_id: int) -> dict:
    """Manually force-dispatch a violation batch, regardless of window expiry."""
    from app.daemon.dispatcher import _dispatch_single_batch
    async with db_engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT rule_id, status FROM dq_results.violation_batches WHERE id = :id"),
            {"id": batch_id},
        )).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    if row["status"] == "dispatched":
        raise HTTPException(status_code=400, detail="Batch already dispatched.")
    await _dispatch_single_batch(batch_id, row["rule_id"])
    return {"detail": f"Batch {batch_id} dispatched."}


@router.post("/violation-batches/{batch_id}/re-enrich", status_code=status.HTTP_202_ACCEPTED)
async def re_enrich_batch(batch_id: int) -> dict:
    """Triggers a manual AI re-enrichment of a batch, appending a new version."""
    from app.services.llm.orchestrator import generate_batch_summary
    from app.daemon.worker import _run_async
    async with db_engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT id FROM dq_results.violation_batches WHERE id = :id"),
            {"id": batch_id},
        )).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Batch not found.")

    # Fire and forget re-enrichment with force=True
    _run_async(generate_batch_summary(batch_id, force=True))
    return {"detail": f"Re-enrichment triggered for batch {batch_id}."}


@router.get("/metrics", response_model=dict)
async def get_system_metrics() -> dict:
    """Returns high-level system observability metrics."""
    async with db_engine.connect() as conn:
        batches_stats = (await conn.execute(text("""
            SELECT 
                COUNT(*) as total_batches,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_batches,
                SUM(CASE WHEN status = 'dispatched' THEN 1 ELSE 0 END) as dispatched_batches,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_batches,
                SUM(total_occurrences) as total_occurrences
            FROM dq_results.violation_batches
        """))).mappings().first()

        llm_stats = (await conn.execute(text("""
            SELECT 
                COUNT(*) as total_enrichments,
                SUM(CASE WHEN parsing_failure = true THEN 1 ELSE 0 END) as parsing_failures,
                AVG(token_usage) as avg_token_usage
            FROM dq_results.llm_summaries
        """))).mappings().first()
        
        events_stats = (await conn.execute(text("""
            SELECT COUNT(*) as total_events FROM dq_results.violation_events
        """))).mappings().first()

    total_enrichments = llm_stats["total_enrichments"] or 0
    parsing_failures = int(llm_stats["parsing_failures"] or 0)
    success_rate = 0
    if total_enrichments > 0:
        success_rate = ((total_enrichments - parsing_failures) / total_enrichments) * 100
        
    total_events = events_stats["total_events"] or 0
    total_batches = batches_stats["total_batches"] or 0
    suppression_rate = 0
    if total_events > 0:
        # Number of duplicate events suppressed = total_events - total_batches dispatched/open
        suppression_rate = ((total_events - total_batches) / total_events) * 100

    return {
        "total_events": total_events,
        "total_batches": total_batches,
        "open_batches": int(batches_stats["open_batches"] or 0),
        "dispatched_batches": int(batches_stats["dispatched_batches"] or 0),
        "failed_batches": int(batches_stats["failed_batches"] or 0),
        "enrichment_success_rate": round(success_rate, 2),
        "enrichment_failure_rate": round(100 - success_rate, 2) if total_enrichments > 0 else 0,
        "avg_token_usage": round(llm_stats["avg_token_usage"] or 0, 2),
        "duplicate_suppression_rate": round(suppression_rate, 2),
    }


# ---------------------------------------------------------------------------
# Human Feedback / Governance endpoints
# ---------------------------------------------------------------------------

@router.post("/violation-batches/{batch_id}/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(batch_id: int, body: FeedbackCreate) -> dict:
    """
    Submit human feedback (accept/reject/edit/annotate) against a batch's latest AI summary.
    Never mutates the original llm_summaries row — stores feedback separately for auditability.
    """
    # Resolve the latest llm_summary for this batch internally
    async with db_engine.connect() as conn:
        summary_row = (await conn.execute(
            text("""
                SELECT id, effective_confidence, prompt_version
                FROM dq_results.llm_summaries
                WHERE violation_batch_id = :batch_id
                ORDER BY created_at DESC LIMIT 1
            """),
            {"batch_id": batch_id},
        )).mappings().first()

    if summary_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No AI enrichment found for this batch. Generate an enrichment first.",
        )

    import json
    edited_fixes_json = json.dumps(body.edited_fixes) if body.edited_fixes is not None else None

    async with db_engine.begin() as conn:
        result = (await conn.execute(
            text("""
                INSERT INTO dq_results.llm_feedback
                    (violation_batch_id, llm_summary_id, feedback_type,
                     edited_summary, edited_fixes, feedback_notes, user_id)
                VALUES
                    (:batch_id, :summary_id, :feedback_type,
                     :edited_summary, :edited_fixes, :feedback_notes, :user_id)
                RETURNING id, created_at
            """),
            {
                "batch_id": batch_id,
                "summary_id": summary_row["id"],
                "feedback_type": body.feedback_type,
                "edited_summary": body.edited_summary,
                "edited_fixes": edited_fixes_json,
                "feedback_notes": body.feedback_notes,
                "user_id": body.user_id,
            },
        )).mappings().first()

    return {
        "id": result["id"],
        "batch_id": batch_id,
        "llm_summary_id": summary_row["id"],
        "feedback_type": body.feedback_type,
        "created_at": result["created_at"].isoformat(),
        "detail": f"Feedback '{body.feedback_type}' recorded for batch {batch_id}.",
    }


@router.get("/violation-batches/{batch_id}/feedback", response_model=list[FeedbackResponse])
async def get_feedback_history(batch_id: int) -> list[FeedbackResponse]:
    """
    Returns the complete audit history of human feedback for this batch,
    including original AI output alongside any human corrections.
    """
    import json
    async with db_engine.connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT
                    f.id,
                    f.violation_batch_id,
                    f.llm_summary_id,
                    f.feedback_type,
                    f.edited_summary,
                    f.edited_fixes,
                    f.feedback_notes,
                    f.user_id,
                    f.created_at,
                    ls.summary          AS original_summary,
                    ls.suggested_fixes  AS original_fixes,
                    ls.effective_confidence AS confidence_level,
                    ls.prompt_version
                FROM dq_results.llm_feedback f
                JOIN dq_results.llm_summaries ls ON ls.id = f.llm_summary_id
                WHERE f.violation_batch_id = :batch_id
                ORDER BY f.created_at ASC
            """),
            {"batch_id": batch_id},
        )).mappings().all()

    results = []
    for r in rows:
        # Parse stored JSON list for original and edited fixes
        raw_orig_fixes = r["original_fixes"]
        if isinstance(raw_orig_fixes, str):
            try:
                orig_fixes = json.loads(raw_orig_fixes)
            except (json.JSONDecodeError, TypeError):
                orig_fixes = []
        else:
            orig_fixes = raw_orig_fixes or []

        edited_fixes_raw = r["edited_fixes"]
        if edited_fixes_raw:
            try:
                edited_fixes = json.loads(edited_fixes_raw)
            except (json.JSONDecodeError, TypeError):
                edited_fixes = None
        else:
            edited_fixes = None

        results.append(FeedbackResponse(
            id=r["id"],
            violation_batch_id=r["violation_batch_id"],
            llm_summary_id=r["llm_summary_id"],
            feedback_type=r["feedback_type"],
            edited_summary=r["edited_summary"],
            edited_fixes=edited_fixes,
            feedback_notes=r["feedback_notes"],
            user_id=r["user_id"],
            created_at=r["created_at"].isoformat(),
            original_summary=r["original_summary"] or "",
            original_fixes=orig_fixes,
            confidence_level=r["confidence_level"] or "unknown",
            prompt_version=r["prompt_version"] or "unknown",
        ))

    return results

