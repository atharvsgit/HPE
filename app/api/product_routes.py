from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import text

from app.daemon import executor, registry
from app.daemon.cron import CronValidationError, classify_scheduler_status
from app.daemon.sql_safety import SQLSafetyError
from app.db.session import metadata_engine
from app.models.product import (
    AISettingsUpdateRequest,
    AppSettingsResponse,
    AssistantApproveRequest,
    AssistantPlanRequest,
    AssistantPlanResponse,
    DashboardSummary,
    DatabaseConnectionCreate,
    DatabaseConnectionResponse,
    DatabaseSchemaResponse,
    DatabaseTestResponse,
    JobCreateRequest,
    JobResponse,
    JobUpdateRequest,
    NotificationSettingsUpdateRequest,
    NotificationDeliveryResponse,
)
from app.models.requests import SavedRuleCreateRequest
from app.models.responses import RuleExecutionResult, SavedRuleResponse
from app.services.assistant_planner import create_assistant_plan
from app.services.database_connections import (
    DuplicateDatabaseConnectionError,
    create_database_connection,
    delete_database_connection,
    get_database_schema,
    list_database_connections,
    test_database_connection,
)
from app.services.schedule_parser import ScheduleParseError, parse_schedule_to_cron
from app.services.runtime_settings import (
    get_settings_payload,
    save_ai_settings,
    save_notification_settings,
)

product_router = APIRouter(tags=["Product Workspace"])


@product_router.post("/databases", response_model=DatabaseConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_database(request: DatabaseConnectionCreate) -> DatabaseConnectionResponse:
    try:
        return await create_database_connection(request)
    except DuplicateDatabaseConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "DUPLICATE_DATABASE_CONNECTION",
                "message": str(exc),
                "existing_connection_id": exc.existing_connection_id,
            },
        ) from exc


@product_router.get("/databases", response_model=list[DatabaseConnectionResponse])
async def list_databases() -> list[DatabaseConnectionResponse]:
    return await list_database_connections()


@product_router.post("/databases/{database_id}/test", response_model=DatabaseTestResponse)
async def test_database(database_id: int) -> DatabaseTestResponse:
    try:
        return await test_database_connection(database_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@product_router.get("/databases/{database_id}/schema", response_model=DatabaseSchemaResponse)
async def database_schema(database_id: int) -> DatabaseSchemaResponse:
    try:
        return await get_database_schema(database_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@product_router.delete("/databases/{database_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_database(database_id: int) -> Response:
    if not await delete_database_connection(database_id):
        raise HTTPException(status_code=404, detail="Database connection not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@product_router.get("/settings", response_model=AppSettingsResponse)
async def app_settings() -> AppSettingsResponse:
    return AppSettingsResponse(**await get_settings_payload())


@product_router.patch("/settings/ai", response_model=AppSettingsResponse)
async def update_ai_settings(request: AISettingsUpdateRequest) -> AppSettingsResponse:
    try:
        return AppSettingsResponse(**await save_ai_settings(request.provider, request.model, request.api_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@product_router.patch("/settings/notifications", response_model=AppSettingsResponse)
async def update_notification_settings(request: NotificationSettingsUpdateRequest) -> AppSettingsResponse:
    return AppSettingsResponse(**await save_notification_settings(request.model_dump(exclude_unset=True)))


@product_router.post("/assistant/plan", response_model=AssistantPlanResponse)
async def assistant_plan(request: AssistantPlanRequest) -> AssistantPlanResponse:
    try:
        return await create_assistant_plan(request)
    except registry.DuplicateRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "DUPLICATE_RULE",
                "message": str(exc),
                "existing_rule_id": exc.existing_rule_id,
            },
        ) from exc
    except (ValueError, SQLSafetyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@product_router.post("/assistant/approve", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def assistant_approve(request: AssistantApproveRequest) -> JobResponse:
    job = JobCreateRequest(
        database_connection_id=request.plan.database_id,
        rule_name=request.plan.rule_name,
        sql=request.plan.sql,
        expected_result=request.plan.expected_result,
        schedule_text=request.plan.schedule_text,
        schedule_cron=request.plan.schedule_cron,
        severity=request.plan.severity,
        notification_channels=request.plan.notification_channels,
        table_name=request.plan.table_name,
    )
    return await create_job(job)


@product_router.get("/orchestrator/jobs", response_model=list[JobResponse])
async def list_jobs() -> list[JobResponse]:
    rules = await registry.list_rules()
    return [await _job_from_rule(rule) for rule in rules]


@product_router.post("/orchestrator/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(request: JobCreateRequest) -> JobResponse:
    try:
        schedule_cron = request.schedule_cron or parse_schedule_to_cron(request.schedule_text)
        rule = await registry.create_rule(
            SavedRuleCreateRequest(
                database_connection_id=request.database_connection_id,
                rule_name=request.rule_name,
                sql=request.sql,
                expected_result=request.expected_result,
                schedule_text=request.schedule_text,
                schedule_cron=schedule_cron,
                is_enabled=request.is_enabled,
                severity=request.severity,
                notification_channels=request.notification_channels,
                source_prompt=request.source_prompt,
                table_name=request.table_name,
            )
        )
    except registry.DuplicateRuleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "type": "DUPLICATE_RULE",
                "message": str(exc),
                "existing_rule_id": exc.existing_rule_id,
            },
        ) from exc
    except (CronValidationError, ScheduleParseError, SQLSafetyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _job_from_rule(rule)


@product_router.patch("/orchestrator/jobs/{job_id}", response_model=JobResponse)
async def update_job(job_id: int, request: JobUpdateRequest) -> JobResponse:
    provided_fields = request.model_fields_set
    schedule_text = registry.UNSET
    schedule_cron = registry.UNSET

    try:
        if "schedule_text" in provided_fields:
            schedule_text = _clean_schedule_text(request.schedule_text)
            schedule_cron = parse_schedule_to_cron(schedule_text)
        elif "schedule_cron" in provided_fields:
            schedule_cron = request.schedule_cron

        rule = await registry.update_rule(
            job_id,
            schedule_text=schedule_text,
            schedule_cron=schedule_cron,
            severity=request.severity,
            notification_channels=request.notification_channels,
            is_enabled=request.is_enabled,
        )
    except (CronValidationError, ScheduleParseError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if rule is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return await _job_from_rule(rule)


@product_router.post("/orchestrator/jobs/{job_id}/run", response_model=RuleExecutionResult)
async def run_job(job_id: int) -> RuleExecutionResult:
    rule = await registry.get_rule(job_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return await executor.execute_rule(registry.execution_request_from_saved_rule(rule))


@product_router.post("/orchestrator/jobs/{job_id}/pause", response_model=JobResponse)
async def pause_job(job_id: int) -> JobResponse:
    rule = await registry.update_rule(job_id, is_enabled=False)
    if rule is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return await _job_from_rule(rule)


@product_router.post("/orchestrator/jobs/{job_id}/resume", response_model=JobResponse)
async def resume_job(job_id: int) -> JobResponse:
    rule = await registry.update_rule(job_id, is_enabled=True)
    if rule is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return await _job_from_rule(rule)


@product_router.delete("/orchestrator/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: int) -> Response:
    if not await registry.delete_rule(job_id):
        raise HTTPException(status_code=404, detail="Job not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@product_router.get("/alerts", response_model=list[dict])
async def list_alerts(limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    async with metadata_engine.connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT v.id, v.rule_id, r.rule_name, r.table_name, v.severity,
                       v.violation_count, v.sample_rows, v.status, v.created_at
                FROM dq_results.violation_events v
                LEFT JOIN dq_config.dq_rules r ON r.rule_id = v.rule_id
                ORDER BY v.created_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )).mappings().all()

        # Collect unique rule_ids to fetch related notification deliveries.
        # Use a formatted IN clause — asyncpg does not support binding Python
        # lists via ANY(:param), so we build the list directly from validated
        # integer IDs (safe: these come from the database, not user input).
        rule_ids = list({int(row["rule_id"]) for row in rows if row["rule_id"] is not None})
        notifications_by_rule: dict = {}
        if rule_ids:
            id_list = ", ".join(str(rid) for rid in rule_ids)
            notif_rows = (await conn.execute(
                text(f"""
                    SELECT id, rule_id, channel, status, error_message, sent_at
                    FROM dq_results.notification_deliveries
                    WHERE rule_id IN ({id_list})
                    ORDER BY sent_at DESC
                """),
            )).mappings().all()
            for notif in notif_rows:
                rid = notif["rule_id"]
                notifications_by_rule.setdefault(rid, []).append({
                    "id": notif["id"],
                    "channel": notif["channel"],
                    "status": notif["status"],
                    "error_message": notif["error_message"],
                    "sent_at": notif["sent_at"].isoformat() if notif["sent_at"] else None,
                })

    result = []
    for row in rows:
        alert = dict(row)
        if alert.get("created_at"):
            alert["created_at"] = alert["created_at"].isoformat()
        alert["notifications"] = notifications_by_rule.get(alert["rule_id"], [])
        result.append(alert)
    return result


@product_router.get("/notifications", response_model=list[NotificationDeliveryResponse])
async def list_notifications(limit: int = Query(default=50, ge=1, le=200)) -> list[NotificationDeliveryResponse]:
    async with metadata_engine.connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT id, rule_id, channel, status, error_message, sent_at
                FROM dq_results.notification_deliveries
                ORDER BY sent_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )).mappings().all()
    return [NotificationDeliveryResponse(**dict(row)) for row in rows]


@product_router.get("/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary() -> DashboardSummary:
    async with metadata_engine.connect() as conn:
        database_count = int((await conn.execute(text("SELECT COUNT(*) FROM dq_config.database_connections"))).scalar_one())
        active_job_count = int((await conn.execute(text("SELECT COUNT(*) FROM dq_config.dq_rules WHERE is_enabled = true"))).scalar_one())
        failure_count_today = int((await conn.execute(text("""
            SELECT COUNT(*)
            FROM dq_results.test_results
            WHERE status IN ('FAIL', 'ERROR')
              AND executed_at >= date_trunc('day', NOW())
        """))).scalar_one())
        latest = (await conn.execute(text("""
            SELECT result_id, rule_id, rule_name, status, observed_value, executed_at
            FROM dq_results.test_results
            ORDER BY executed_at DESC
            LIMIT 8
        """))).mappings().all()
        notification_rows = (await conn.execute(text("""
            SELECT status, COUNT(*) AS count
            FROM dq_results.notification_deliveries
            GROUP BY status
        """))).mappings().all()
    return DashboardSummary(
        database_count=database_count,
        active_job_count=active_job_count,
        failure_count_today=failure_count_today,
        latest_results=[dict(row) for row in latest],
        notification_counts={row["status"]: row["count"] for row in notification_rows},
    )


async def _job_from_rule(rule: SavedRuleResponse) -> JobResponse:
    last_status = None
    last_observed_value = None
    last_run_at = None
    async with metadata_engine.connect() as conn:
        row = (await conn.execute(
            text("""
                SELECT status, observed_value, executed_at
                FROM dq_results.test_results
                WHERE rule_id = :rule_id
                ORDER BY executed_at DESC, result_id DESC
                LIMIT 1
            """),
            {"rule_id": rule.rule_id},
        )).mappings().first()
        if row:
            last_status = row["status"]
            last_observed_value = _json_number(row["observed_value"])
            last_run_at = row["executed_at"]

    return JobResponse(
        id=rule.rule_id,
        database_connection_id=rule.database_connection_id,
        database_name=rule.database_name,
        table_name=rule.table_name,
        rule_name=rule.rule_name,
        sql=rule.sql,
        expected_result=rule.expected_result,
        schedule_text=rule.schedule_text,
        schedule_cron=rule.schedule_cron,
        is_enabled=rule.is_enabled,
        severity=rule.severity,
        notification_channels=rule.notification_channels,
        scheduler_status=str(classify_scheduler_status(rule.is_enabled, rule.schedule_cron)),
        last_status=last_status,
        last_observed_value=last_observed_value,
        last_run_at=last_run_at,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _json_number(value):
    if value is None:
        return None
    try:
        if value == value.to_integral_value():
            return int(value)
    except AttributeError:
        return value
    return float(value)


def _clean_schedule_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
