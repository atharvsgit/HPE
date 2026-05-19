"""
app/models/platform_requests.py
---------------------------------
Pydantic v2 request models for all Platform Intelligence API endpoints.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PipelineTriggerRequest(BaseModel):
    """Request body for triggering a full pipeline run."""

    table_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Fully-qualified PostgreSQL table name (e.g. business_data.employees). "
            "Must be accessible to the dq_executor role for read-only profiling."
        ),
    )


class PipelineScheduleCreateRequest(BaseModel):
    """Request body for creating a recurring platform pipeline schedule."""

    table_name: str = Field(..., min_length=1, max_length=200)
    schedule_cron: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="5-field cron expression interpreted in UTC.",
    )
    is_enabled: bool = Field(default=True)
    description: str | None = Field(default=None, max_length=500)


class PipelineScheduleUpdateRequest(BaseModel):
    """Request body for enabling/disabling a recurring platform schedule."""

    is_enabled: bool = Field(...)


class ProfileRequest(BaseModel):
    """Request body for profiling a single table."""

    table_name: str = Field(..., min_length=1, max_length=200)
    row_limit: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        description="Override the global profiling_row_limit for this request.",
    )


class RuleSuggestionRequest(BaseModel):
    """Request body for generating rule suggestions for a table."""

    table_name: str = Field(..., min_length=1, max_length=200)
    backend: Literal["heuristic", "gemini"] = Field(
        default="heuristic",
        description=(
            "Suggestion backend. 'heuristic' works offline with no API key. "
            "'gemini' calls Gemini 2.5 Flash and requires GEMINI_API_KEY."
        ),
    )


class ApplySuggestionRequest(BaseModel):
    """Request body for applying a rule suggestion as a saved rule."""

    schedule_cron: str | None = Field(
        default=None,
        description="Optional 5-field cron expression for scheduling the applied rule.",
    )
    is_enabled: bool = Field(
        default=True,
        description="Whether the new saved rule should be active immediately.",
    )


class AnomalyDetectionRequest(BaseModel):
    """Request body for running anomaly detection on a table column."""

    table_name: str = Field(..., min_length=1, max_length=200)
    columns: list[str] = Field(
        ...,
        min_length=1,
        description="List of numeric column names to analyse.",
    )
    method: Literal["isolation_forest", "zscore", "lof"] = Field(
        default="isolation_forest",
        description=(
            "Detection algorithm: "
            "'isolation_forest' (sklearn IsolationForest), "
            "'zscore' (scipy z-score threshold), "
            "'lof' (sklearn LocalOutlierFactor)."
        ),
    )


class DriftDetectionRequest(BaseModel):
    """Request body for running drift detection between two tables."""

    reference_table: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Baseline / reference table (e.g. historical snapshot).",
    )
    current_table: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Current / production table to compare against the reference.",
    )
    columns: list[str] = Field(
        ...,
        min_length=1,
        description="Columns to check for drift. Must exist in both tables.",
    )
