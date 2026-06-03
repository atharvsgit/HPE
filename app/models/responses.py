from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.requests import ExpectedResult


class ErrorDetail(BaseModel):
    type: str
    message: str


class AIEnrichment(BaseModel):
    ai_summary: str | None = None
    root_causes: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    confidence_score: str | None = None
    prompt_version: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    token_usage: int | None = None
    parsing_failure: bool = False


class RuleExecutionResult(BaseModel):
    rule_id: int | None = None
    database_connection_id: int | None = None
    rule_name: str
    status: Literal["PASS", "FAIL", "ERROR"]
    result: dict[str, int | float] | None
    violation_rows: list[dict[str, Any]] = []
    expected_result: ExpectedResult
    execution_time_ms: int
    executed_at: datetime
    error: ErrorDetail | None
    ai_enrichment: AIEnrichment | None = None


class SavedRuleResponse(BaseModel):
    rule_id: int
    database_connection_id: int | None = None
    database_name: str | None = None
    table_name: str | None = None
    rule_name: str
    sql: str
    expected_result: ExpectedResult
    schedule_text: str | None = None
    schedule_cron: str | None
    notification_channels: list[str] = Field(default_factory=lambda: ["slack"])
    is_enabled: bool
    severity: Literal["critical", "high", "medium", "low"]
    created_at: datetime
    updated_at: datetime


class SavedRuleExecutionResultResponse(BaseModel):
    result_id: int
    rule_id: int | None
    rule_name: str
    sql: str
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


class DatabaseConnectionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset: dict[str, Any]
    table_schema: list[dict[str, Any]] = Field(default_factory=list, alias="schema")
    rows: list[dict[str, Any]] = []
    message: str
