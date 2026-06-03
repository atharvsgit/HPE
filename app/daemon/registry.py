from __future__ import annotations

import json
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


_RULE_SELECT = """
    SELECT
        r.rule_id,
        r.database_connection_id,
        dc.name AS database_name,
        r.table_name,
        r.rule_name,
        r.sql_text,
        r.expected_result_type,
        r.expected_result_value,
        r.is_enabled,
        r.schedule_cron,
        r.schedule_text,
        r.notification_channels,
        r.severity,
        r.created_at,
        r.updated_at
    FROM dq_config.dq_rules r
    LEFT JOIN dq_config.database_connections dc ON dc.id = r.database_connection_id
"""


async def create_rule(rule: SavedRuleCreateRequest) -> SavedRuleResponse:
    validate_safe_select(rule.sql)
    validate_cron_expression(rule.schedule_cron)
    async with db_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO dq_config.dq_rules (
                    database_connection_id,
                    rule_name,
                    sql_text,
                    expected_result_type,
                    expected_result_value,
                    is_enabled,
                    schedule_cron,
                    schedule_text,
                    severity,
                    table_name,
                    notification_channels,
                    source_prompt
                )
                VALUES (
                    :database_connection_id,
                    :rule_name,
                    :sql_text,
                    :expected_result_type,
                    :expected_result_value,
                    :is_enabled,
                    :schedule_cron,
                    :schedule_text,
                    :severity,
                    :table_name,
                    CAST(:notification_channels AS jsonb),
                    :source_prompt
                )
                RETURNING rule_id
                """
            ),
            {
                "database_connection_id": rule.database_connection_id,
                "rule_name": rule.rule_name,
                "sql_text": rule.sql,
                "expected_result_type": rule.expected_result.type,
                "expected_result_value": rule.expected_result.value,
                "is_enabled": rule.is_enabled,
                "schedule_cron": rule.schedule_cron,
                "schedule_text": rule.schedule_text,
                "severity": rule.severity,
                "table_name": rule.table_name,
                "notification_channels": json.dumps(rule.notification_channels),
                "source_prompt": rule.source_prompt,
            },
        )
        rule_id = result.scalar_one()
    saved_rule = await get_rule(rule_id)
    if saved_rule is None:
        raise RuntimeError("Saved rule could not be loaded after creation.")
    return saved_rule


async def list_rules() -> list[SavedRuleResponse]:
    async with db_engine.connect() as conn:
        result = await conn.execute(text(f"{_RULE_SELECT} ORDER BY r.rule_id"))
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
            text(f"{_RULE_SELECT} WHERE r.rule_id = :rule_id"),
            {"rule_id": rule_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return _saved_rule_from_row(row)


async def update_rule(
    rule_id: int,
    *,
    schedule_text: str | None = None,
    schedule_cron: str | None = None,
    severity: str | None = None,
    notification_channels: list[str] | None = None,
    is_enabled: bool | None = None,
) -> SavedRuleResponse | None:
    validate_cron_expression(schedule_cron)

    assignments = ["updated_at = NOW()"]
    params: dict = {"rule_id": rule_id}

    if schedule_text is not None:
        assignments.append("schedule_text = :schedule_text")
        params["schedule_text"] = schedule_text
    if schedule_cron is not None:
        assignments.append("schedule_cron = :schedule_cron")
        params["schedule_cron"] = schedule_cron
    if severity is not None:
        assignments.append("severity = :severity")
        params["severity"] = severity
    if notification_channels is not None:
        assignments.append("notification_channels = CAST(:notification_channels AS jsonb)")
        params["notification_channels"] = json.dumps(notification_channels)
    if is_enabled is not None:
        assignments.append("is_enabled = :is_enabled")
        params["is_enabled"] = is_enabled

    async with db_engine.begin() as conn:
        result = await conn.execute(
            text(
                f"""
                UPDATE dq_config.dq_rules
                SET {", ".join(assignments)}
                WHERE rule_id = :rule_id
                RETURNING rule_id
                """
            ),
            params,
        )
        if result.scalar_one_or_none() is None:
            return None

    return await get_rule(rule_id)


async def delete_rule(rule_id: int) -> bool:
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                """
                UPDATE dq_results.test_results
                SET rule_id = NULL
                WHERE rule_id = :rule_id
                """
            ),
            {"rule_id": rule_id},
        )
        result = await conn.execute(
            text(
                """
                DELETE FROM dq_config.dq_rules
                WHERE rule_id = :rule_id
                RETURNING rule_id
                """
            ),
            {"rule_id": rule_id},
        )
        return result.scalar_one_or_none() is not None


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
        database_connection_id=rule.database_connection_id,
        rule_name=rule.rule_name,
        sql=rule.sql,
        expected_result=rule.expected_result,
    )


def _saved_rule_from_row(row) -> SavedRuleResponse:
    return SavedRuleResponse(
        rule_id=row["rule_id"],
        database_connection_id=row["database_connection_id"],
        database_name=row["database_name"],
        table_name=row["table_name"],
        rule_name=row["rule_name"],
        sql=row["sql_text"],
        expected_result=ExpectedResult(
            type=row["expected_result_type"],
            value=row["expected_result_value"],
        ),
        schedule_text=row["schedule_text"],
        schedule_cron=row["schedule_cron"],
        notification_channels=_json_list(row["notification_channels"]),
        is_enabled=row["is_enabled"],
        severity=row["severity"],
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


def _json_list(value) -> list[str]:
    if value is None:
        return ["slack"]
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else ["slack"]
        except json.JSONDecodeError:
            return ["slack"]
    return list(value)
