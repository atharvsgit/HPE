"""
LLM route integration tests.
All DB and LLM calls are mocked so these run without a live database.
"""
from datetime import datetime, UTC

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.llm.models import LLMDraftResponse, LLMRuleCandidate
from app.models.requests import ExpectedResult
from app.models.responses import SavedRuleResponse


client = TestClient(app)


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


def _make_saved_rule(rule_id: int = 42) -> SavedRuleResponse:
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


def test_create_draft(monkeypatch) -> None:
    mock_candidate = LLMRuleCandidate(
        rule_name="Mock Rule",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees",
        expected_result=ExpectedResult(type="zero_violations"),
    )

    async def mock_generate_draft(self, intent):
        return mock_candidate

    async def mock_create_draft(intent, candidate, validation_status, validation_errors, dry_run_res):
        return _make_draft()

    monkeypatch.setattr("app.llm.provider.MockLLMProvider.generate_draft", mock_generate_draft)
    monkeypatch.setattr("app.llm.drafts.create_draft", mock_create_draft)

    response = client.post("/llm/rules/draft", json={"prompt": "Check something", "dry_run": False})
    assert response.status_code == 201
    body = response.json()
    assert body["validation_status"] == "valid"
    assert body["reviewer_status"] == "pending_review"
    assert body["draft_id"] == 1


def test_list_drafts(monkeypatch) -> None:
    async def mock_list_drafts():
        return [_make_draft(1), _make_draft(2)]

    monkeypatch.setattr("app.llm.drafts.list_drafts", mock_list_drafts)

    response = client.get("/llm/rules/drafts")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_draft(monkeypatch) -> None:
    async def mock_get_draft(draft_id):
        return _make_draft(draft_id)

    monkeypatch.setattr("app.llm.drafts.get_draft", mock_get_draft)

    response = client.get("/llm/rules/drafts/1")
    assert response.status_code == 200
    assert response.json()["draft_id"] == 1


def test_get_draft_not_found(monkeypatch) -> None:
    async def mock_get_draft(draft_id):
        return None

    monkeypatch.setattr("app.llm.drafts.get_draft", mock_get_draft)

    response = client.get("/llm/rules/drafts/999")
    assert response.status_code == 404


def test_approve_draft(monkeypatch) -> None:
    async def mock_approve_draft(draft_id):
        return _make_draft(draft_id, reviewer_status="approved", approved_rule_id=42)

    monkeypatch.setattr("app.llm.drafts.approve_draft", mock_approve_draft)

    response = client.post("/llm/rules/drafts/1/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["reviewer_status"] == "approved"
    assert body["approved_rule_id"] == 42


def test_approve_invalid_draft_rejected(monkeypatch) -> None:
    async def mock_approve_draft(draft_id):
        raise ValueError("Only valid drafts can be approved")

    monkeypatch.setattr("app.llm.drafts.approve_draft", mock_approve_draft)

    response = client.post("/llm/rules/drafts/1/approve")
    assert response.status_code == 400
    assert "valid" in response.json()["detail"].lower()


def test_reject_draft(monkeypatch) -> None:
    async def mock_update_reviewer_status(draft_id, status, notes=None):
        return _make_draft(draft_id, reviewer_status=status)

    monkeypatch.setattr("app.llm.drafts.update_reviewer_status", mock_update_reviewer_status)

    response = client.post(
        "/llm/rules/drafts/1/reject",
        json={"reviewer_notes": "Bad logic in SQL"}
    )
    assert response.status_code == 200
    assert response.json()["reviewer_status"] == "rejected"


def test_request_changes(monkeypatch) -> None:
    async def mock_update_reviewer_status(draft_id, status, notes=None):
        return _make_draft(draft_id, reviewer_status=status)

    monkeypatch.setattr("app.llm.drafts.update_reviewer_status", mock_update_reviewer_status)

    response = client.post(
        "/llm/rules/drafts/1/request-changes",
        json={"reviewer_notes": "Use department-specific checks"}
    )
    assert response.status_code == 200
    assert response.json()["reviewer_status"] == "changes_requested"
