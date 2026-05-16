from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.requests import ExpectedResult


class LLMDraftRequest(BaseModel):
    prompt: str
    schedule_cron: str | None = None
    dry_run: bool = True


class LLMRuleCandidate(BaseModel):
    rule_name: str
    sql: str
    expected_result: ExpectedResult
    schedule_cron: str | None = None


class LLMDraftDryRunResult(BaseModel):
    status: Literal["PASS", "FAIL", "ERROR", "not_run"]
    observed_key: str | None = None
    observed_value: float | None = None
    error_message: str | None = None


class LLMDraftResponse(BaseModel):
    draft_id: int
    source_prompt: str
    rule_name: str | None
    sql: str | None
    expected_result: ExpectedResult | None
    schedule_cron: str | None
    validation_status: str
    validation_errors: list[str]
    dry_run: LLMDraftDryRunResult | None
    reviewer_status: str
    reviewer_notes: str | None = None
    approved_rule_id: int | None = None
    created_at: datetime
    updated_at: datetime


class LLMDraftReviewRequest(BaseModel):
    reviewer_notes: str
