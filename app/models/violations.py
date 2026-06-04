from datetime import datetime
from typing import Any, Literal
from decimal import Decimal

from pydantic import BaseModel


class NotificationPolicy(BaseModel):
    id: int
    rule_id: int
    immediate_threshold: Decimal | None
    batch_window_minutes: int
    deduplication_window_minutes: int
    enable_llm_summary: bool
    enable_fix_suggestions: bool
    slack_enabled: bool
    email_enabled: bool
    created_at: datetime


class ViolationEvent(BaseModel):
    id: int
    rule_result_id: int
    rule_id: int
    severity: Literal["critical", "high", "medium", "low"]
    violation_count: Decimal | None
    sample_rows: list[dict[str, Any]] | None
    fingerprint: str
    status: Literal["open", "dispatched", "resolved", "failed"]
    created_at: datetime


class ViolationBatch(BaseModel):
    id: int
    rule_id: int
    severity: Literal["critical", "high", "medium", "low"]
    first_seen: datetime
    last_seen: datetime
    total_occurrences: int
    total_violation_count: Decimal | None
    status: Literal["open", "dispatching", "enriched", "dispatched", "resolved", "failed"]
    ai_enrichment: dict[str, Any] | None = None


class ViolationBatchSendRequest(BaseModel):
    pass
