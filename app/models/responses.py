from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.requests import ExpectedResult


class ErrorDetail(BaseModel):
    type: str
    message: str


class RuleExecutionResult(BaseModel):
    rule_id: int | None = None
    rule_name: str
    status: Literal["PASS", "FAIL", "ERROR"]
    result: dict[str, int | float] | None
    expected_result: ExpectedResult
    execution_time_ms: int
    executed_at: datetime
    error: ErrorDetail | None


class SavedRuleResponse(BaseModel):
    rule_id: int
    rule_name: str
    sql: str
    expected_result: ExpectedResult
    schedule_cron: str | None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class SavedRuleExecutionResultResponse(BaseModel):
    result_id: int
    rule_id: int | None
    rule_name: str
    status: Literal["PASS", "FAIL", "ERROR"]
    observed_key: str | None
    observed_value: int | float | None
    execution_time_ms: int | None
    error_message: str | None
    executed_at: datetime


class SchedulerRuleStatusResponse(BaseModel):
    rule_id: int
    rule_name: str
    is_enabled: bool
    schedule_cron: str | None
    scheduler_status: Literal[
        "schedulable",
        "disabled",
        "missing_schedule",
        "invalid_cron",
    ]
