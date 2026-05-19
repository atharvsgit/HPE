from decimal import Decimal

from sqlalchemy import text

from app.daemon.cron import classify_scheduler_status, validate_cron_expression
from app.daemon.sql_safety import validate_safe_select
from app.db.session import metadata_engine as db_engine
from app.models.requests import ExpectedResult, RuleExecutionRequest, SavedRuleCreateRequest
from app.models.responses import (
    SavedRuleExecutionResultResponse,
    SavedRuleResponse,
    SchedulerRuleStatusResponse,
)


async def create_rule(rule: SavedRuleCreateRequest) -> SavedRuleResponse:
    validate_safe_select(rule.sql)
    validate_cron_expression(rule.schedule_cron)
    async with db_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO dq_config.dq_rules (
                    rule_name,
                    sql_text,
                    expected_result_type,
                    expected_result_value,
                    is_enabled,
                    schedule_cron
                )
                VALUES (
                    :rule_name,
                    :sql_text,
                    :expected_result_type,
                    :expected_result_value,
                    :is_enabled,
                    :schedule_cron
                )
                RETURNING
                    rule_id,
                    rule_name,
                    sql_text,
                    expected_result_type,
                    expected_result_value,
                    is_enabled,
                    schedule_cron,
                    created_at,
                    updated_at
                """
            ),
            {
                "rule_name": rule.rule_name,
                "sql_text": rule.sql,
                "expected_result_type": rule.expected_result.type,
                "expected_result_value": rule.expected_result.value,
                "is_enabled": rule.is_enabled,
                "schedule_cron": rule.schedule_cron,
            },
        )
        return _saved_rule_from_row(result.mappings().one())


async def list_rules() -> list[SavedRuleResponse]:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    rule_id,
                    rule_name,
                    sql_text,
                    expected_result_type,
                    expected_result_value,
                    is_enabled,
                    schedule_cron,
                    created_at,
                    updated_at
                FROM dq_config.dq_rules
                ORDER BY rule_id
                """
            )
        )
        return [_saved_rule_from_row(row) for row in result.mappings().all()]


async def list_scheduler_rule_statuses() -> list[SchedulerRuleStatusResponse]:
    rules = await list_rules()
    return [
        SchedulerRuleStatusResponse(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            is_enabled=rule.is_enabled,
            schedule_cron=rule.schedule_cron,
            scheduler_status=classify_scheduler_status(rule.is_enabled, rule.schedule_cron),
        )
        for rule in rules
    ]


async def list_schedulable_rules() -> list[SavedRuleResponse]:
    rules = await list_rules()
    return [
        rule
        for rule in rules
        if classify_scheduler_status(rule.is_enabled, rule.schedule_cron) == "schedulable"
    ]


async def get_rule(rule_id: int) -> SavedRuleResponse | None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    rule_id,
                    rule_name,
                    sql_text,
                    expected_result_type,
                    expected_result_value,
                    is_enabled,
                    schedule_cron,
                    created_at,
                    updated_at
                FROM dq_config.dq_rules
                WHERE rule_id = :rule_id
                """
            ),
            {"rule_id": rule_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return _saved_rule_from_row(row)


async def list_rule_results(
    rule_id: int,
    limit: int = 20,
) -> list[SavedRuleExecutionResultResponse]:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    result_id,
                    rule_id,
                    rule_name,
                    sql_text,
                    status,
                    observed_key,
                    observed_value,
                    execution_time_ms,
                    error_message,
                    executed_at
                FROM dq_results.test_results
                WHERE rule_id = :rule_id
                ORDER BY executed_at DESC, result_id DESC
                LIMIT :limit
                """
            ),
            {"rule_id": rule_id, "limit": limit},
        )
        return [_result_from_row(row) for row in result.mappings().all()]


async def list_all_results(limit: int = 50) -> list[SavedRuleExecutionResultResponse]:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    result_id,
                    rule_id,
                    rule_name,
                    sql_text,
                    status,
                    observed_key,
                    observed_value,
                    execution_time_ms,
                    error_message,
                    executed_at
                FROM dq_results.test_results
                ORDER BY executed_at DESC, result_id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return [_result_from_row(row) for row in result.mappings().all()]


def execution_request_from_saved_rule(rule: SavedRuleResponse) -> RuleExecutionRequest:
    return RuleExecutionRequest(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        sql=rule.sql,
        expected_result=rule.expected_result,
    )


def _saved_rule_from_row(row) -> SavedRuleResponse:
    return SavedRuleResponse(
        rule_id=row["rule_id"],
        rule_name=row["rule_name"],
        sql=row["sql_text"],
        expected_result=ExpectedResult(
            type=row["expected_result_type"],
            value=row["expected_result_value"],
        ),
        schedule_cron=row["schedule_cron"],
        is_enabled=row["is_enabled"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _result_from_row(row) -> SavedRuleExecutionResultResponse:
    return SavedRuleExecutionResultResponse(
        result_id=row["result_id"],
        rule_id=row["rule_id"],
        rule_name=row["rule_name"],
        sql=row["sql_text"],
        status=row["status"],
        observed_key=row["observed_key"],
        observed_value=_json_number(row["observed_value"]),
        execution_time_ms=row["execution_time_ms"],
        error_message=row["error_message"],
        executed_at=row["executed_at"],
    )


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)
