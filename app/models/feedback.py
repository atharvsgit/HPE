import html
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FeedbackCreate(BaseModel):
    feedback_type: Literal["accept", "reject", "edit", "annotate"]
    edited_summary: str | None = Field(None, max_length=5000)
    edited_fixes: list[str] | None = Field(None, max_length=10)
    feedback_notes: str | None = Field(None, max_length=2000)
    user_id: str = Field("system", max_length=100)

    @field_validator("edited_summary", "feedback_notes")
    @classmethod
    def sanitize_text(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Basic sanitization to prevent HTML/script injection
        # Escape HTML chars, which neutralizes <script> tags and markdown abuse
        return html.escape(v.strip())

    @field_validator("edited_fixes")
    @classmethod
    def sanitize_fixes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        return [html.escape(fix.strip()) for fix in v if fix.strip()]


class FeedbackResponse(BaseModel):
    id: int
    violation_batch_id: int
    llm_summary_id: int
    feedback_type: str
    edited_summary: str | None = None
    edited_fixes: list[str] | None = None
    feedback_notes: str | None = None
    user_id: str
    created_at: str
    
    # Audit trail context from the linked AI summary
    original_summary: str
    original_fixes: list[str]
    confidence_level: str
    prompt_version: str
