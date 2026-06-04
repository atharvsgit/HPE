from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ExpectedResult(BaseModel):
    type: Literal["zero_violations", "min_threshold", "max_threshold", "equals"]
    value: Decimal | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "ExpectedResult":
        if self.type == "zero_violations":
            return self
        if self.value is None:
            raise ValueError(f"expected_result.value is required for {self.type}.")
        return self

    @property
    def decimal_value(self) -> Decimal:
        if self.value is None:
            raise ValueError(f"expected_result.value is required for {self.type}.")
        return self.value


class RuleExecutionRequest(BaseModel):
    rule_id: int | None = None
    database_connection_id: int | None = None
    rule_name: str = Field(..., min_length=1, max_length=300)
    sql: str = Field(..., min_length=1)
    expected_result: ExpectedResult
    notification_channels: list[Literal["slack", "email"]] = Field(
        default_factory=lambda: ["slack", "email"]
    )


class SavedRuleCreateRequest(BaseModel):
    database_connection_id: int | None = None
    rule_name: str = Field(..., min_length=1, max_length=300)
    sql: str = Field(..., min_length=1)
    expected_result: ExpectedResult
    schedule_cron: str | None = None
    schedule_text: str | None = None
    table_name: str | None = None
    notification_channels: list[Literal["slack", "email"]] = Field(default_factory=lambda: ["slack"])
    source_prompt: str | None = None
    is_enabled: bool = True
    severity: Literal["critical", "high", "medium", "low"] = "medium"


class DatabaseConnectionRequest(BaseModel):
    source_type: Literal["database"] = "database"
    sub_type: Literal["postgresql"] = "postgresql"
    config: dict[str, Any]
