from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.db.session import metadata_engine as db_engine
from app.models.responses import AlertContext, RuleExecutionResult

logger = logging.getLogger(__name__)


async def attach_alert_context(
    result: RuleExecutionResult,
    *,
    rule_id: int,
    batch_id: int | None,
    deduplication_window_minutes: int | None = None,
) -> None:
    try:
        result._alert_context = await build_alert_context(
            rule_id=rule_id,
            batch_id=batch_id,
            executed_at=result.executed_at,
            deduplication_window_minutes=deduplication_window_minutes,
        )
    except Exception:
        logger.exception("Failed to build alert context for rule %s.", rule_id)


async def build_alert_context(
    *,
    rule_id: int,
    batch_id: int | None,
    executed_at: datetime,
    deduplication_window_minutes: int | None = None,
) -> AlertContext:
    window_minutes = await _deduplication_window_minutes(rule_id, deduplication_window_minutes)
    window_started_at = executed_at - timedelta(minutes=window_minutes) if window_minutes > 0 else executed_at

    recent_failure_count = 0
    recent_observed_total = 0
    batch_occurrences = None
    batch_violation_count = None
    batch_first_seen = None
    batch_last_seen = None

    async with db_engine.connect() as conn:
        recent_row = (await conn.execute(
            text(
                """
                SELECT
                    COUNT(*) AS failure_count,
                    COALESCE(SUM(observed_value), 0) AS observed_total
                FROM dq_results.test_results
                WHERE rule_id = :rule_id
                  AND status IN ('FAIL', 'ERROR')
                  AND executed_at >= :window_started_at
                  AND executed_at <= :window_ended_at
                """
            ),
            {
                "rule_id": rule_id,
                "window_started_at": window_started_at,
                "window_ended_at": executed_at,
            },
        )).mappings().one()
        recent_failure_count = int(recent_row["failure_count"] or 0)
        recent_observed_total = _json_number(recent_row["observed_total"])

        if batch_id is not None:
            batch_row = (await conn.execute(
                text(
                    """
                    SELECT total_occurrences, total_violation_count, first_seen, last_seen
                    FROM dq_results.violation_batches
                    WHERE id = :batch_id
                    """
                ),
                {"batch_id": batch_id},
            )).mappings().first()
            if batch_row:
                batch_occurrences = int(batch_row["total_occurrences"] or 0)
                batch_violation_count = _json_number(batch_row["total_violation_count"])
                batch_first_seen = batch_row["first_seen"]
                batch_last_seen = batch_row["last_seen"]

    return AlertContext(
        batch_id=batch_id,
        deduplication_window_minutes=window_minutes,
        recent_failure_count=recent_failure_count,
        recent_observed_total=recent_observed_total,
        window_started_at=window_started_at,
        window_ended_at=executed_at,
        batch_occurrences=batch_occurrences,
        batch_violation_count=batch_violation_count,
        batch_first_seen=batch_first_seen,
        batch_last_seen=batch_last_seen,
    )


async def _deduplication_window_minutes(rule_id: int, provided: int | None) -> int:
    if provided is not None:
        return max(0, int(provided))

    async with db_engine.connect() as conn:
        value = (await conn.execute(
            text(
                """
                SELECT deduplication_window_minutes
                FROM dq_config.notification_policies
                WHERE rule_id = :rule_id
                """
            ),
            {"rule_id": rule_id},
        )).scalar_one_or_none()
    return max(0, int(value or 0))


def _json_number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    return value
