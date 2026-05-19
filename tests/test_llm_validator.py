import pytest
from app.llm.validator import validate_candidate as validate_draft
from app.llm.models import LLMRuleCandidate
from app.models.requests import ExpectedResult

@pytest.mark.asyncio
async def test_valid_llm_candidate():
    candidate = LLMRuleCandidate(
        rule_name="Valid Rule",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees;",
        expected_result=ExpectedResult(type="zero_violations")
    )
    status, errors, dry_run = await validate_draft(candidate, dry_run=False)
    assert status == "valid"
    assert len(errors) == 0
    assert dry_run is None

@pytest.mark.asyncio
async def test_unsafe_sql_rejected():
    candidate = LLMRuleCandidate(
        rule_name="Unsafe Rule",
        sql="DELETE FROM business_data.employees;",
        expected_result=ExpectedResult(type="zero_violations")
    )
    status, errors, dry_run = await validate_draft(candidate, dry_run=False)
    assert status == "invalid"
    assert len(errors) > 0

@pytest.mark.asyncio
async def test_invalid_cron_rejected():
    candidate = LLMRuleCandidate(
        rule_name="Invalid Cron Rule",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees;",
        expected_result=ExpectedResult(type="zero_violations"),
        schedule_cron="invalid_cron"
    )
    status, errors, dry_run = await validate_draft(candidate, dry_run=False)
    assert status == "invalid"
    assert any("cron" in err.lower() for err in errors)

@pytest.mark.asyncio
async def test_dry_run_fail_does_not_block_review(monkeypatch):
    candidate = LLMRuleCandidate(
        rule_name="Failing Dry Run Rule",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees;",
        expected_result=ExpectedResult(type="zero_violations")
    )
    
    from app.models.responses import RuleExecutionResult
    from datetime import datetime, UTC
    
    async def fake_execute_rule(rule, persist=True):
        assert persist is False
        return RuleExecutionResult(
            rule_id=None,
            rule_name=rule.rule_name,
            status="FAIL",
            result={"violation_count": 10},
            expected_result=rule.expected_result,
            execution_time_ms=10,
            executed_at=datetime.now(UTC),
            error=None
        )
        
    monkeypatch.setattr("app.llm.validator.execute_rule", fake_execute_rule)
    status, errors, dry_run = await validate_draft(candidate, dry_run=True)
    
    # FAIL dry-run should not make status invalid
    assert status == "valid"
    assert dry_run is not None
    assert dry_run.status == "FAIL"
    assert dry_run.observed_value == 10
