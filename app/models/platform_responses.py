"""
app/models/platform_responses.py
----------------------------------
Pydantic v2 response models for all Platform Intelligence API endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class PipelineRunResponse(BaseModel):
    """Response for pipeline run creation and status queries."""

    run_id: int
    table_name: str
    status: Literal["PENDING", "RUNNING", "SUCCESS", "FAILED"]
    triggered_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class DatasetProfileResponse(BaseModel):
    """Response returned after profiling a table."""

    profile_id: int
    run_id: int | None = None
    table_name: str
    row_count: int
    column_count: int
    null_summary: dict[str, float]
    schema_info: dict[str, str]
    statistics: dict[str, Any]
    uniqueness: dict[str, Any]
    profiled_at: datetime


class RuleSuggestionResponse(BaseModel):
    """A single generated rule suggestion."""

    suggestion_id: int
    profile_id: int | None = None
    table_name: str
    column_name: str
    suggestion_type: Literal["heuristic", "gemini"]
    suggested_rule_name: str
    suggested_sql: str
    expected_result_type: str
    expected_result_value: float | None = None
    confidence: float
    applied: bool
    applied_rule_id: int | None = None
    created_at: datetime


class AnomalyResultResponse(BaseModel):
    """A single anomaly detection result for one column."""

    anomaly_id: int
    run_id: int | None = None
    table_name: str
    column_name: str
    method: str
    anomaly_count: int
    total_rows: int
    anomaly_pct: float
    details: dict[str, Any] | None = None
    detected_at: datetime


class ColumnDriftResultResponse(BaseModel):
    """Drift result for a single column."""

    column_name: str
    stat_test: str
    drift_score: float
    is_drifted: bool


class DriftResultResponse(BaseModel):
    """Full drift detection response for a reference vs current table comparison."""

    reference_table: str
    current_table: str
    columns: list[str]
    column_results: list[ColumnDriftResultResponse]
    dataset_drift_detected: bool
    share_drifted_columns: float
    detected_at: datetime


class PipelineTriggerResponse(BaseModel):
    """Immediate response when a pipeline is triggered (before it completes)."""

    run_id: int
    table_name: str
    status: Literal["PENDING"]
    message: str = "Pipeline triggered. Use GET /platform/pipeline/runs/{run_id} to check status."
