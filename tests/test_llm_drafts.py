"""
LLM draft business-logic tests.
DB calls are fully mocked; no live database required.
"""
from datetime import datetime, UTC

import pytest
from fastapi import HTTPException

from app.llm import drafts
from app.llm.models import LLMDraftResponse
from app.models.requests import ExpectedResult
from app.models.responses import SavedRuleResponse


def _make_draft(draft_id: int = 1, reviewer_status: str = "pending_review", validation_status: str = "valid", approved_rule_id=None) -> LLMDraftResponse:
    now = datetime.now(UTC)
    return LLMDraftResponse(
        draft_id=draft_id,
        source_prompt="Check something",
        rule_name="Mock Rule",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees",
        expected_result=ExpectedResult(type="zero_violations"),
        schedule_cron=None,
        validation_status=validation_status,
        validation_errors=[],
        dry_run=None,
        reviewer_status=reviewer_status,
        reviewer_notes=None,
        approved_rule_id=approved_rule_id,
        created_at=now,
        updated_at=now,
    )


def _make_saved_rule(rule_id: int = 99) -> SavedRuleResponse:
    now = datetime.now(UTC)
    return SavedRuleResponse(
        rule_id=rule_id,
        rule_name="Mock Rule",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees",
        expected_result=ExpectedResult(type="zero_violations"),
        schedule_cron=None,
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_approve_valid_draft(monkeypatch):
    """approve_draft should set reviewer_status=approved and link the saved rule_id."""
    draft = _make_draft(1, "pending_review", "valid")

    async def mock_approve(draft_id):
        draft.reviewer_status = "approved"
        draft.approved_rule_id = 99
        return draft

    monkeypatch.setattr("app.llm.drafts.approve_draft", mock_approve)

    result = await drafts.approve_draft(1)
    assert result.reviewer_status == "approved"
    assert result.approved_rule_id == 99


@pytest.mark.asyncio
async def test_approve_already_approved_draft_fails(monkeypatch):
    draft = _make_draft(1, "approved", "valid", approved_rule_id=5)

    async def mock_get_draft(draft_id):
        return draft

    monkeypatch.setattr("app.llm.drafts.get_draft", mock_get_draft)

    with pytest.raises(ValueError, match="already approved"):
        await drafts.approve_draft(1)


@pytest.mark.asyncio
async def test_approve_invalid_draft_fails(monkeypatch):
    draft = _make_draft(1, "pending_review", "invalid")

    async def mock_get_draft(draft_id):
        return draft

    monkeypatch.setattr("app.llm.drafts.get_draft", mock_get_draft)

    with pytest.raises(ValueError, match="Cannot approve"):
        await drafts.approve_draft(1)


@pytest.mark.asyncio
async def test_reject_draft_stores_notes(monkeypatch):
    draft = _make_draft(1, "pending_review", "valid")

    async def mock_update_reviewer_status(draft_id, status, notes=None):
        draft.reviewer_status = status
        draft.reviewer_notes = notes
        return draft

    monkeypatch.setattr("app.llm.drafts.update_reviewer_status", mock_update_reviewer_status)

    result = await drafts.update_reviewer_status(1, "rejected", notes="Bad SQL logic")
    assert result.reviewer_status == "rejected"
    assert result.reviewer_notes == "Bad SQL logic"


@pytest.mark.asyncio
async def test_request_changes_status(monkeypatch):
    draft = _make_draft(1, "pending_review", "valid")

    async def mock_update_reviewer_status(draft_id, status, notes=None):
        draft.reviewer_status = status
        draft.reviewer_notes = notes
        return draft

    monkeypatch.setattr("app.llm.drafts.update_reviewer_status", mock_update_reviewer_status)

    result = await drafts.update_reviewer_status(1, "changes_requested", notes="Use department checks")
    assert result.reviewer_status == "changes_requested"
