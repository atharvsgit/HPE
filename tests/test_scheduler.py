import asyncio
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


def _duplicate_saved_rule(rule_id: int) -> SavedRuleResponse:
    base_rule = _saved_rule()
    return base_rule.model_copy(update={"rule_id": rule_id, "rule_name": f"Duplicate {rule_id}"})


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


class FakeJob:
    def __init__(self, job_id: str, trigger, args) -> None:
        self.id = job_id
        self.trigger = trigger
        self.args = args


class FakeScheduler:
    def __init__(self, existing_job: FakeJob | None = None) -> None:
        self.existing_job = existing_job
        self.add_calls = []
        self.removed_jobs = []

    def get_job(self, job_id: str):
        if self.existing_job and self.existing_job.id == job_id:
            return self.existing_job
        return None

    def add_job(self, *args, **kwargs) -> None:
        self.add_calls.append((args, kwargs))

    def get_jobs(self) -> list[FakeJob]:
        return [self.existing_job] if self.existing_job else []

    def remove_job(self, job_id: str) -> None:
        self.removed_jobs.append(job_id)


@pytest.mark.asyncio
async def test_load_scheduled_rules_does_not_replace_unchanged_job(monkeypatch) -> None:
    rule = _saved_rule()
    existing_job = FakeJob(
        "dq_rule_7",
        scheduler.cron_to_trigger(rule.schedule_cron or ""),
        [rule],
    )
    fake_scheduler = FakeScheduler(existing_job)

    async def fake_list_rules():
        return [rule]

    monkeypatch.setattr(scheduler.registry, "list_rules", fake_list_rules)

    count = await scheduler.load_scheduled_rules(fake_scheduler)

    assert count == 1
    assert fake_scheduler.add_calls == []
    assert fake_scheduler.removed_jobs == []


@pytest.mark.asyncio
async def test_load_scheduled_rules_skips_equivalent_duplicate_rows(monkeypatch) -> None:
    fake_scheduler = FakeScheduler()

    async def fake_list_rules():
        return [_saved_rule(), _duplicate_saved_rule(8)]

    monkeypatch.setattr(scheduler.registry, "list_rules", fake_list_rules)

    count = await scheduler.load_scheduled_rules(fake_scheduler)

    assert count == 1
    assert len(fake_scheduler.add_calls) == 1
    assert fake_scheduler.add_calls[0][1]["id"] == "dq_rule_7"


@pytest.mark.asyncio
async def test_refresh_scheduled_rules_survives_one_load_error(monkeypatch) -> None:
    calls = 0
    recovered = False

    async def fake_load_scheduled_rules(_scheduler):
        nonlocal calls, recovered
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary load failure")
        recovered = True

    monkeypatch.setattr(scheduler, "load_scheduled_rules", fake_load_scheduled_rules)
    task = asyncio.create_task(
        scheduler.refresh_scheduled_rules(FakeScheduler(), interval_seconds=0.01)
    )

    try:
        for _ in range(20):
            if recovered:
                break
            await asyncio.sleep(0.01)
        assert recovered
        assert calls >= 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
