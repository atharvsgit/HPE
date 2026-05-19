from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.daemon.evaluator import evaluate_observed_value
from app.daemon.sql_safety import SQLSafetyError, strip_trailing_semicolon, validate_safe_select
from app.db.session import engine as db_engine
from app.models.requests import RuleExecutionRequest
from app.models.responses import ErrorDetail, RuleExecutionResult
from app.daemon.notifier import notify_admin_of_failure
from app.settings import get_settings


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _numeric_value(raw_value: Any) -> Decimal:
    if isinstance(raw_value, bool):
        raise ValueError("Boolean values are not valid aggregate results.")
    if isinstance(raw_value, Decimal):
        return raw_value
    if isinstance(raw_value, int):
        return Decimal(raw_value)
    if isinstance(raw_value, float):
        return Decimal(str(raw_value))
    raise ValueError(f"Expected a numeric aggregate result, got {type(raw_value).__name__}.")


def _error_type(exc: Exception) -> str:
    message = str(exc).lower()
    if "statement timeout" in message or "query canceled" in message:
        return "SQL_TIMEOUT"
    return "SQL_EXECUTION_ERROR"


async def execute_rule(rule: RuleExecutionRequest) -> RuleExecutionResult:
    started = time.perf_counter()
    executed_at = datetime.now(UTC)
    settings = get_settings()

    try:
        validate_safe_select(rule.sql)
        sql_body = strip_trailing_semicolon(rule.sql)
    except SQLSafetyError as exc:
        result = RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status="ERROR",
            result=None,
            expected_result=rule.expected_result,
            execution_time_ms=_elapsed_ms(started),
            executed_at=executed_at,
            error=ErrorDetail(type=exc.code, message=str(exc)),
        )
        await _persist_result(rule, result, None, None)
        return result

    observed_key: str | None = None
    observed_value: Decimal | None = None

    try:
        wrapped_sql = f"SELECT * FROM ({sql_body}) AS dq_rule_result LIMIT 2"
        async with db_engine.connect() as conn:
            async with conn.begin():
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                await conn.execute(
                    text(f"SET LOCAL statement_timeout = '{settings.statement_timeout_ms}ms'")
                )
                query_result = await conn.execute(text(wrapped_sql))
                rows = query_result.mappings().all()

        if len(rows) != 1:
            raise ResultShapeError(f"Expected exactly one result row, got {len(rows)}.")

        row = dict(rows[0])
        if len(row) != 1:
            raise ResultShapeError(f"Expected exactly one result column, got {len(row)}.")

        observed_key, raw_value = next(iter(row.items()))
        if observed_key not in {"violation_count", "observed_value"}:
            raise ResultShapeError(
                "Aggregate column must be named either violation_count or observed_value."
            )

        observed_value = _numeric_value(raw_value)
        status = evaluate_observed_value(observed_value, rule.expected_result)
        result = RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status=status,
            result={observed_key: _json_number(observed_value)},
            expected_result=rule.expected_result,
            execution_time_ms=_elapsed_ms(started),
            executed_at=executed_at,
            error=None,
        )
    except ResultShapeError as exc:
        result = RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status="ERROR",
            result=None,
            expected_result=rule.expected_result,
            execution_time_ms=_elapsed_ms(started),
            executed_at=executed_at,
            error=ErrorDetail(type="SQL_RESULT_SHAPE_ERROR", message=str(exc)),
        )
    except (ValueError, InvalidOperation) as exc:
        result = RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status="ERROR",
            result=None,
            expected_result=rule.expected_result,
            execution_time_ms=_elapsed_ms(started),
            executed_at=executed_at,
            error=ErrorDetail(type="SQL_RESULT_TYPE_ERROR", message=str(exc)),
        )
    except SQLAlchemyError as exc:
        result = RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status="ERROR",
            result=None,
            expected_result=rule.expected_result,
            execution_time_ms=_elapsed_ms(started),
            executed_at=executed_at,
            error=ErrorDetail(type=_error_type(exc), message=str(exc)),
        )
    except Exception as exc:
        result = RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status="ERROR",
            result=None,
            expected_result=rule.expected_result,
            execution_time_ms=_elapsed_ms(started),
            executed_at=executed_at,
            error=ErrorDetail(type="UNKNOWN_ERROR", message=str(exc)),
        )

    await _persist_result(rule, result, observed_key, observed_value)
    
    # Trigger admin notification logic
    await notify_admin_of_failure(rule, result)
    
    return result


class ResultShapeError(Exception):
    pass


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


async def _persist_result(
    rule: RuleExecutionRequest,
    result: RuleExecutionResult,
    observed_key: str | None,
    observed_value: Decimal | None,
) -> None:
    error_message = None
    if result.error is not None:
        error_message = f"{result.error.type}: {result.error.message}"

    try:
        async with db_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO dq_results.test_results (
                        rule_id,
                        rule_name,
                        sql_text,
                        status,
                        observed_key,
                        observed_value,
                        execution_time_ms,
                        error_message,
                        executed_at
                    )
                    VALUES (
                        :rule_id,
                        :rule_name,
                        :sql_text,
                        :status,
                        :observed_key,
                        :observed_value,
                        :execution_time_ms,
                        :error_message,
                        :executed_at
                    )
                    """
                ),
                {
                    "rule_id": rule.rule_id,
                    "rule_name": rule.rule_name,
                    "sql_text": rule.sql,
                    "status": result.status,
                    "observed_key": observed_key,
                    "observed_value": observed_value,
                    "execution_time_ms": result.execution_time_ms,
                    "error_message": error_message,
                    "executed_at": result.executed_at,
                },
            )
    except Exception:
        # Persistence failure should not hide the rule execution outcome from the API caller.
        return
