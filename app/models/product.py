from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.requests import ExpectedResult


class DatabaseConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    db_type: Literal["postgresql"] = "postgresql"
    host: str = Field(..., min_length=1)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class DatabaseConnectionResponse(BaseModel):
    id: int
    name: str
    db_type: Literal["postgresql"]
    host: str
    port: int
    database: str
    username: str
    status: Literal["untested", "connected", "failed"]
    last_tested_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DatabaseTestResponse(BaseModel):
    id: int
    status: Literal["connected", "failed"]
    message: str
    table_count: int = 0


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool


class TableInfo(BaseModel):
    schema_name: str
    table_name: str
    qualified_name: str
    columns: list[ColumnInfo]


class DatabaseSchemaResponse(BaseModel):
    database_id: int
    tables: list[TableInfo]


class AssistantPlanRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    database_id: int | None = None


class AssistantPlanResponse(BaseModel):
    generation_id: int | None = None
    database_id: int
    database_name: str
    table_name: str
    rule_name: str
    sql: str
    expected_result: ExpectedResult
    schedule_text: str
    schedule_cron: str | None
    severity: Literal["critical", "high", "medium", "low"]
    notification_channels: list[Literal["slack", "email"]]
    explanation: str
    confidence: Literal["high", "medium", "low"]
    source: Literal["gemini", "openai", "anthropic", "openrouter", "groq", "heuristic"]
    dry_run: dict[str, Any] | None = None


class AssistantApproveRequest(BaseModel):
    plan: AssistantPlanResponse


class JobCreateRequest(BaseModel):
    database_connection_id: int
    rule_name: str = Field(..., min_length=1, max_length=300)
    sql: str = Field(..., min_length=1)
    expected_result: ExpectedResult
    schedule_text: str | None = None
    schedule_cron: str | None = None
    severity: Literal["critical", "high", "medium", "low"] = "critical"
    notification_channels: list[Literal["slack", "email"]] = Field(default_factory=lambda: ["slack"])
    is_enabled: bool = True
    source_prompt: str | None = None
    table_name: str | None = None


class JobUpdateRequest(BaseModel):
    schedule_text: str | None = None
    schedule_cron: str | None = None
    severity: Literal["critical", "high", "medium", "low"] | None = None
    notification_channels: list[Literal["slack", "email"]] | None = None
    is_enabled: bool | None = None


class JobResponse(BaseModel):
    id: int
    database_connection_id: int | None
    database_name: str | None
    table_name: str | None
    rule_name: str
    sql: str
    expected_result: ExpectedResult
    schedule_text: str | None
    schedule_cron: str | None
    is_enabled: bool
    severity: Literal["critical", "high", "medium", "low"]
    notification_channels: list[str]
    scheduler_status: str
    last_status: str | None = None
    last_observed_value: int | float | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DashboardSummary(BaseModel):
    database_count: int
    active_job_count: int
    failure_count_today: int
    latest_results: list[dict[str, Any]]
    notification_counts: dict[str, int]


class NotificationDeliveryResponse(BaseModel):
    id: int
    rule_id: int | None
    channel: Literal["slack", "email"]
    status: Literal["sent", "failed", "skipped"]
    error_message: str | None
    sent_at: datetime


class AIProviderOption(BaseModel):
    id: Literal["gemini", "openai", "anthropic", "openrouter", "groq"]
    label: str
    default_model: str


class AISettingsResponse(BaseModel):
    provider: Literal["gemini", "openai", "anthropic", "openrouter", "groq"]
    model: str
    has_api_key: bool
    masked_api_key: str = ""
    providers: list[AIProviderOption]


class NotificationSettingsResponse(BaseModel):
    admin_email: str = ""
    notification_email_from: str = ""
    smtp_server: str = ""
    smtp_port: int | None = None
    smtp_username: str = ""
    smtp_use_tls: bool = True
    has_smtp_password: bool = False
    masked_smtp_password: str = ""
    slack_configured: bool = False
    masked_slack_webhook: str = ""


class AppSettingsResponse(BaseModel):
    ai: AISettingsResponse
    notifications: NotificationSettingsResponse


class AISettingsUpdateRequest(BaseModel):
    provider: Literal["gemini", "openai", "anthropic", "openrouter", "groq"]
    model: str | None = None
    api_key: str | None = None


class NotificationSettingsUpdateRequest(BaseModel):
    admin_email: str | None = None
    notification_email_from: str | None = None
    smtp_server: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    slack_webhook_url: str | None = None
