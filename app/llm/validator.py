from pydantic import ValidationError

from app.daemon.cron import validate_cron_expression
from app.daemon.executor import execute_rule
from app.daemon.sql_safety import SQLSafetyError, validate_safe_select
from app.llm.models import LLMDraftDryRunResult, LLMRuleCandidate
from app.models.requests import RuleExecutionRequest


async def validate_candidate(candidate: LLMRuleCandidate, dry_run: bool) -> tuple[str, list[str], LLMDraftDryRunResult | None]:
    errors: list[str] = []
    
    # Static Validation
    try:
        validate_safe_select(candidate.sql)
    except SQLSafetyError as e:
        errors.append(f"SQL Safety Error: {str(e)}")

    if candidate.schedule_cron:
        try:
            validate_cron_expression(candidate.schedule_cron)
        except ValueError as e:
            errors.append(f"Cron Error: {str(e)}")
            
    # Model shape validation handles expected_result, 
    # but we can explicitly catch errors if they slip through the initial parse.
    try:
        req = RuleExecutionRequest(
            rule_name=candidate.rule_name,
            sql=candidate.sql,
            expected_result=candidate.expected_result
        )
    except ValidationError as e:
        errors.append(f"Model Validation Error: {str(e)}")

    status = "valid" if not errors else "invalid"
    
    # Dry Run
    dry_run_res = None
    if dry_run and not errors:
        result = await execute_rule(req, persist=False)
        dry_run_res = LLMDraftDryRunResult(
            status=result.status,
            observed_key=next(iter(result.result)) if result.result else None,
            observed_value=float(next(iter(result.result.values()))) if result.result else None,
            error_message=result.error.message if result.error else None
        )
        if result.status == "ERROR" and getattr(result.error, "type", "") == "SQL_RESULT_SHAPE_ERROR":
            errors.append(f"Dry Run Error: {result.error.message}")
            status = "invalid"

    return status, errors, dry_run_res
