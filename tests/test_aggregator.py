from datetime import datetime, UTC
from typing import Any

import pytest
from unittest.mock import AsyncMock

from app.models.requests import RuleExecutionRequest, ExpectedResult
from app.models.responses import RuleExecutionResult
from app.models.violations import ViolationBatch
from app.services.violations import aggregator


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "FakeResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        return self._rows[0]["id"] if self._rows and "id" in self._rows[0] else None

    def scalar_one(self) -> Any:
        if not self._rows or "id" not in self._rows[0]:
            raise ValueError("No scalar found")
        return self._rows[0]["id"]


class FakeConnection:
    def __init__(self, fake_engine: "FakeEngine") -> None:
        self.fake_engine = fake_engine

    def begin(self) -> "FakeTransaction":
        return FakeTransaction()
        
    async def __aenter__(self) -> "FakeConnection":
        return self
        
    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass

    async def execute(self, statement, params=None) -> FakeResult:
        sql = str(statement).lstrip().upper()
        self.fake_engine.queries.append((sql, params))

        if "SELECT SEVERITY FROM DQ_CONFIG.DQ_RULES" in sql:
            return FakeResult([{"severity": self.fake_engine.severity}])
            
        if "SELECT ID FROM DQ_RESULTS.VIOLATION_BATCHES" in sql:
            return FakeResult([{"id": self.fake_engine.batch_id}] if self.fake_engine.batch_id else [])
            
        if "INSERT INTO DQ_RESULTS.VIOLATION_BATCHES" in sql:
            self.fake_engine.batch_id = 999
            return FakeResult([{"id": 999}])
            
        return FakeResult()


class FakeTransaction:
    async def __aenter__(self) -> "FakeTransaction":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


class FakeEngine:
    def __init__(self, severity: str = "medium", batch_id: int | None = None) -> None:
        self.severity = severity
        self.batch_id = batch_id
        self.queries: list[tuple[str, dict | None]] = []
        self.connection = FakeConnection(self)

    def connect(self) -> FakeConnection:
        return self.connection

    def begin(self) -> FakeConnection:
        return self.connection


class FakePolicy:
    def __init__(self, window: int = 15):
        self.deduplication_window_minutes = window


@pytest.fixture
def base_rule() -> RuleExecutionRequest:
    return RuleExecutionRequest(
        rule_id=1,
        rule_name="Test Rule",
        sql="SELECT COUNT(*) FROM test",
        expected_result=ExpectedResult(type="zero_violations")
    )


@pytest.fixture
def base_result(base_rule) -> RuleExecutionResult:
    return RuleExecutionResult(
        rule_id=base_rule.rule_id,
        rule_name=base_rule.rule_name,
        status="FAIL",
        result={"violation_count": 10},
        violation_rows=[],
        expected_result=base_rule.expected_result,
        execution_time_ms=10,
        executed_at=datetime.now(UTC),
        error=None,
    )


@pytest.mark.asyncio
async def test_duplicate_after_dispatched_batch(monkeypatch, base_rule, base_result) -> None:
    # Scenario: is_duplicate is True, no open batch exists because it was dispatched.
    # The new logic should find the recent batch anyway and NOT insert a new batch, nor trigger immediate dispatch.
    
    fake_engine = FakeEngine(severity="medium", batch_id=101)
    monkeypatch.setattr(aggregator, "db_engine", fake_engine)
    
    async def fake_get_policy(rule_id): return FakePolicy()
    monkeypatch.setattr(aggregator, "get_or_create_policy", fake_get_policy)
    
    async def fake_check_duplicate(*args, **kwargs): return True  # is_duplicate = True
    monkeypatch.setattr(aggregator, "check_duplicate_and_increment", fake_check_duplicate)
    
    mock_dispatch = AsyncMock()
    monkeypatch.setattr(aggregator, "_dispatch_batch_immediately", mock_dispatch)

    async def fake_missing_channels(*args, **kwargs): return []
    monkeypatch.setattr(aggregator, "_missing_requested_channels", fake_missing_channels)

    await aggregator.process_violation(base_rule, base_result)

    # Verify that we searched for the batch regardless of status
    batch_query = next((q for q, _ in fake_engine.queries if "ORDER BY FIRST_SEEN DESC" in q), None)
    assert batch_query is not None, "Should search for recent batch ignoring status when duplicate"
    
    # Ensure NO INSERT into violation_events or violation_batches
    insert_events = next((q for q, _ in fake_engine.queries if "INSERT INTO DQ_RESULTS.VIOLATION_EVENTS" in q), None)
    assert insert_events is None, "Should not insert event for duplicate"
    
    insert_batches = next((q for q, _ in fake_engine.queries if "INSERT INTO DQ_RESULTS.VIOLATION_BATCHES" in q), None)
    assert insert_batches is None, "Should not create new batch for duplicate"
    
    # Ensure it updated the existing batch
    update_batch = next((q for q, _ in fake_engine.queries if "UPDATE DQ_RESULTS.VIOLATION_BATCHES" in q), None)
    assert update_batch is not None, "Should increment occurrence count on existing batch"
    
    # Ensure immediate dispatch is not called for non-critical duplicate
    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_critical_severity_duplicate_handling(monkeypatch, base_rule, base_result) -> None:
    # Scenario: critical severity, is_duplicate is True
    # Should NOT trigger immediate dispatch.
    
    fake_engine = FakeEngine(severity="critical", batch_id=101)
    monkeypatch.setattr(aggregator, "db_engine", fake_engine)
    
    async def fake_get_policy(rule_id): return FakePolicy()
    monkeypatch.setattr(aggregator, "get_or_create_policy", fake_get_policy)
    
    async def fake_check_duplicate(*args, **kwargs): return True  # is_duplicate = True
    monkeypatch.setattr(aggregator, "check_duplicate_and_increment", fake_check_duplicate)
    
    mock_dispatch = AsyncMock()
    monkeypatch.setattr(aggregator, "_dispatch_batch_immediately", mock_dispatch)

    async def fake_missing_channels(*args, **kwargs): return []
    monkeypatch.setattr(aggregator, "_missing_requested_channels", fake_missing_channels)

    await aggregator.process_violation(base_rule, base_result)

    mock_dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_dispatches_newly_enabled_channel(monkeypatch, base_rule, base_result) -> None:
    fake_engine = FakeEngine(severity="medium", batch_id=101)
    monkeypatch.setattr(aggregator, "db_engine", fake_engine)
    base_rule.notification_channels = ["slack", "email"]

    async def fake_get_policy(rule_id): return FakePolicy()
    monkeypatch.setattr(aggregator, "get_or_create_policy", fake_get_policy)

    async def fake_check_duplicate(*args, **kwargs): return True
    monkeypatch.setattr(aggregator, "check_duplicate_and_increment", fake_check_duplicate)

    async def fake_missing_channels(rule, batch_id):
        assert batch_id == 101
        assert rule.notification_channels == ["slack", "email"]
        return ["email"]
    monkeypatch.setattr(aggregator, "_missing_requested_channels", fake_missing_channels)

    mock_dispatch = AsyncMock()
    monkeypatch.setattr(aggregator, "_dispatch_batch_immediately", mock_dispatch)

    await aggregator.process_violation(base_rule, base_result)

    mock_dispatch.assert_awaited_once()
    dispatched_rule = mock_dispatch.await_args.args[1]
    assert dispatched_rule.notification_channels == ["email"]


@pytest.mark.asyncio
async def test_duplicate_outside_dedupe_window(monkeypatch, base_rule, base_result) -> None:
    # Scenario: is_duplicate is False (outside dedupe window).
    # Should insert new event, create/update a batch, and dispatch the new failure.
    
    fake_engine = FakeEngine(severity="medium", batch_id=None)  # No open batch
    monkeypatch.setattr(aggregator, "db_engine", fake_engine)
    
    async def fake_get_policy(rule_id): return FakePolicy()
    monkeypatch.setattr(aggregator, "get_or_create_policy", fake_get_policy)
    
    async def fake_check_duplicate(*args, **kwargs): return False  # is_duplicate = False
    monkeypatch.setattr(aggregator, "check_duplicate_and_increment", fake_check_duplicate)
    
    mock_dispatch = AsyncMock()
    monkeypatch.setattr(aggregator, "_dispatch_batch_immediately", mock_dispatch)

    await aggregator.process_violation(base_rule, base_result)

    # Should search for OPEN batch
    batch_query = next((q for q, _ in fake_engine.queries if "AND STATUS = 'OPEN'" in q), None)
    assert batch_query is not None
    
    insert_events = next((q for q, _ in fake_engine.queries if "INSERT INTO DQ_RESULTS.VIOLATION_EVENTS" in q), None)
    assert insert_events is not None
    
    insert_batches = next((q for q, _ in fake_engine.queries if "INSERT INTO DQ_RESULTS.VIOLATION_BATCHES" in q), None)
    assert insert_batches is not None
    
    mock_dispatch.assert_awaited_once()


def test_violation_batch_allows_worker_intermediate_statuses() -> None:
    batch = ViolationBatch(
        id=1,
        rule_id=1,
        severity="medium",
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
        total_occurrences=1,
        total_violation_count=10,
        status="dispatching",
    )

    assert batch.status == "dispatching"
