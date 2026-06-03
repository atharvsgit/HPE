from datetime import UTC, datetime

import pytest

from app.daemon import scheduler
from app.models.requests import ExpectedResult
from app.models.responses import RuleExecutionResult, SavedRuleResponse


def _saved_rule() -> SavedRuleResponse:
    now = datetime(2026, 5, 9, tzinfo=UTC)
    return SavedRuleResponse(
        rule_id=7,
        rule_name="Scheduled salary rule",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE salary < 0;",
        expected_result=ExpectedResult(type="zero_violations"),
        schedule_cron="*/5 * * * *",
        is_enabled=True,
        severity="medium",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_scheduled_rule_execution_calls_existing_executor_path(monkeypatch) -> None:
    calls = []

    async def fake_execute_rule(rule):
        calls.append(rule)
        return RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status="FAIL",
            result={"violation_count": 3},
            expected_result=rule.expected_result,
            execution_time_ms=11,
            executed_at=datetime(2026, 5, 9, tzinfo=UTC),
            error=None,
        )

    monkeypatch.setattr(scheduler.executor, "execute_rule", fake_execute_rule)

    result = await scheduler.execute_scheduled_rule(_saved_rule(), jitter_seconds=0)

    assert result.status == "FAIL"
    assert len(calls) == 1
    assert calls[0].rule_id == 7
    assert calls[0].rule_name == "Scheduled salary rule"
