from fastapi import APIRouter, HTTPException, Query, Response, status

from app.daemon import connection, executor, registry
from app.daemon.cron import CronValidationError
from app.daemon.sql_safety import SQLSafetyError
from app.models.requests import DatabaseConnectionRequest, RuleExecutionRequest, SavedRuleCreateRequest
from app.models.responses import (
    DatabaseConnectionResponse,
    RuleExecutionResult,
    SavedRuleExecutionResultResponse,
    SavedRuleResponse,
    SchedulerRuleStatusResponse,
)

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
