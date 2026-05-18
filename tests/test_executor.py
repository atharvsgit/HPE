from decimal import Decimal

import pytest

from app.daemon import executor
from app.models.requests import ExpectedResult, RuleExecutionRequest


class FakeResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class FakeConnection:
    def __init__(self, fake_engine: "FakeEngine") -> None:
        self.fake_engine = fake_engine

    def begin(self) -> "FakeTransaction":
        return FakeTransaction()

    async def execute(self, statement, params=None) -> FakeResult:
        sql = str(statement)
        if sql.lstrip().upper().startswith("INSERT INTO DQ_RESULTS.TEST_RESULTS"):
            self.fake_engine.inserts.append(params)
            return FakeResult()
        if "SELECT * FROM (" in sql:
            self.fake_engine.select_attempted = True
            return FakeResult(self.fake_engine.rows)
        if sql.lstrip().upper().startswith("SELECT * FROM BUSINESS_DATA.EMPLOYEES"):
            self.fake_engine.preview_attempted = True
            return FakeResult(self.fake_engine.preview_rows)
        return FakeResult()


class FakeConnectionContext:
    def __init__(self, fake_engine: "FakeEngine") -> None:
        self.connection = FakeConnection(fake_engine)

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeTransaction:
    async def __aenter__(self) -> "FakeTransaction":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeEngine:
    def __init__(
        self,
        rows: list[dict[str, object]],
        preview_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.rows = rows
        self.preview_rows = preview_rows or []
        self.inserts: list[dict[str, object]] = []
        self.select_attempted = False
        self.preview_attempted = False

    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(self)

    def begin(self) -> FakeConnectionContext:
        return FakeConnectionContext(self)


@pytest.mark.asyncio
async def test_execute_rule_success(monkeypatch) -> None:
    fake_engine = FakeEngine([{"violation_count": Decimal("0")}])
    monkeypatch.setattr(executor, "db_engine", fake_engine)
    rule = RuleExecutionRequest(
        rule_name="No active employee has negative salary",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE salary < 0;",
        expected_result=ExpectedResult(type="zero_violations"),
    )

    result = await executor.execute_rule(rule)

    assert result.status == "PASS"
    assert result.result == {"violation_count": 0}
    assert fake_engine.select_attempted is True
    assert fake_engine.inserts[0]["status"] == "PASS"


@pytest.mark.asyncio
async def test_execute_rule_failure(monkeypatch) -> None:
    fake_engine = FakeEngine(
        [{"violation_count": Decimal("10")}],
        [{"employee_id": 1, "salary": Decimal("-1000")}],
    )
    monkeypatch.setattr(executor, "db_engine", fake_engine)
    rule = RuleExecutionRequest(
        rule_name="No active employee has negative salary",
        sql="SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE salary < 0;",
        expected_result=ExpectedResult(type="zero_violations"),
    )

    result = await executor.execute_rule(rule)

    assert result.status == "FAIL"
    assert result.result == {"violation_count": 10}
    assert result.violation_rows == [{"employee_id": 1, "salary": -1000}]
    assert fake_engine.preview_attempted is True
    assert fake_engine.inserts[0]["observed_value"] == Decimal("10")


@pytest.mark.asyncio
async def test_execute_rule_rejects_invalid_sql(monkeypatch) -> None:
    fake_engine = FakeEngine([])
    monkeypatch.setattr(executor, "db_engine", fake_engine)
    rule = RuleExecutionRequest(
        rule_name="Dangerous SQL",
        sql="DELETE FROM business_data.employees;",
        expected_result=ExpectedResult(type="zero_violations"),
    )

    result = await executor.execute_rule(rule)

    assert result.status == "ERROR"
    assert result.error is not None
    assert result.error.type == "INVALID_SQL"
    assert fake_engine.select_attempted is False
    assert fake_engine.inserts[0]["status"] == "ERROR"
