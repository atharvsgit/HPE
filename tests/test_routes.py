from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.models.requests import ExpectedResult, SavedRuleCreateRequest
from app.models.responses import (
    DatabaseConnectionResponse,
    RuleExecutionResult,
    SavedRuleExecutionResultResponse,
    SavedRuleResponse,
    SchedulerRuleStatusResponse,
)

client = TestClient(app)


def test_connect_database(monkeypatch) -> None:
    async def fake_connect_database(request) -> DatabaseConnectionResponse:
        assert request.source_type == "database"
        assert request.config["table"] == "business_data.employees"
        return DatabaseConnectionResponse(
            dataset={
                "id": "business_data.employees",
                "name": "business_data.employees",
                "table": "business_data.employees",
                "records": 100000,
            },
            schema=[
                {
                    "columnName": "employee_id",
                    "dataType": "bigint",
                    "nullable": False,
                }
            ],
            rows=[],
            message="Connected to business_data.employees with 100000 rows.",
        )

    monkeypatch.setattr(routes.connection, "connect_database", fake_connect_database)

    response = client.post(
        "/connect-database",
        json={
            "source_type": "database",
            "sub_type": "postgresql",
            "config": {
                "host": "postgres",
                "port": "5432",
                "database": "dq_test",
                "username": "dq_app",
                "password": "dq_app_password",
                "table": "business_data.employees",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["dataset"]["records"] == 100000


def _saved_rule(rule_id: int = 1) -> SavedRuleResponse:
    now = datetime(2026, 5, 9, tzinfo=UTC)
    return SavedRuleResponse(
        rule_id=rule_id,
        rule_name="No active employee has negative salary",
        sql=(
            "SELECT COUNT(*) AS violation_count FROM business_data.employees "
            "WHERE status = 'active' AND salary < 0;"
        ),
        expected_result=ExpectedResult(type="zero_violations"),
        schedule_cron=None,
        is_enabled=True,
        severity="medium",
        created_at=now,
        updated_at=now,
    )


def test_create_rule(monkeypatch) -> None:
    async def fake_create_rule(rule: SavedRuleCreateRequest) -> SavedRuleResponse:
        assert rule.rule_name == "No active employee has negative salary"
        return _saved_rule()

    monkeypatch.setattr(routes.registry, "create_rule", fake_create_rule)

    response = client.post(
        "/rules",
        json={
            "rule_name": "No active employee has negative salary",
            "sql": (
                "SELECT COUNT(*) AS violation_count FROM business_data.employees "
                "WHERE status = 'active' AND salary < 0;"
            ),
            "expected_result": {"type": "zero_violations"},
            "schedule_cron": None,
            "is_enabled": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["rule_id"] == 1


def test_create_rule_rejects_unsafe_sql() -> None:
    response = client.post(
        "/rules",
        json={
            "rule_name": "Unsafe rule",
            "sql": "DELETE FROM business_data.employees;",
            "expected_result": {"type": "zero_violations"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["type"] == "INVALID_SQL"


def test_create_rule_rejects_invalid_cron() -> None:
    response = client.post(
        "/rules",
        json={
            "rule_name": "Invalid schedule",
            "sql": "SELECT COUNT(*) AS observed_value FROM business_data.employees;",
            "expected_result": {"type": "min_threshold", "value": 1},
            "schedule_cron": "61 * * * *",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["type"] == "INVALID_CRON"


def test_list_rules(monkeypatch) -> None:
    async def fake_list_rules() -> list[SavedRuleResponse]:
        return [_saved_rule()]

    monkeypatch.setattr(routes.registry, "list_rules", fake_list_rules)

    response = client.get("/rules")

    assert response.status_code == 200
    assert response.json()[0]["rule_id"] == 1


def test_delete_rule(monkeypatch) -> None:
    async def fake_delete_rule(rule_id: int) -> bool:
        assert rule_id == 1
        return True

    monkeypatch.setattr(routes.registry, "delete_rule", fake_delete_rule)

    response = client.delete("/rules/1")

    assert response.status_code == 204
    assert response.content == b""


def test_delete_rule_not_found(monkeypatch) -> None:
    async def fake_delete_rule(rule_id: int) -> bool:
        assert rule_id == 404
        return False

    monkeypatch.setattr(routes.registry, "delete_rule", fake_delete_rule)

    response = client.delete("/rules/404")

    assert response.status_code == 404


def test_run_saved_rule(monkeypatch) -> None:
    async def fake_get_rule(rule_id: int) -> SavedRuleResponse | None:
        return _saved_rule(rule_id)

    async def fake_execute_rule(rule) -> RuleExecutionResult:
        assert rule.rule_id == 1
        return RuleExecutionResult(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            status="FAIL",
            result={"violation_count": 10},
            expected_result=rule.expected_result,
            execution_time_ms=12,
            executed_at=datetime(2026, 5, 9, tzinfo=UTC),
            error=None,
        )

    monkeypatch.setattr(routes.registry, "get_rule", fake_get_rule)
    monkeypatch.setattr(routes.executor, "execute_rule", fake_execute_rule)

    response = client.post("/rules/1/run")

    assert response.status_code == 200
    assert response.json()["rule_id"] == 1
    assert response.json()["status"] == "FAIL"


def test_retrieve_results_for_saved_rule(monkeypatch) -> None:
    async def fake_get_rule(rule_id: int) -> SavedRuleResponse | None:
        return _saved_rule(rule_id)

    async def fake_list_rule_results(
        rule_id: int,
        limit: int,
    ) -> list[SavedRuleExecutionResultResponse]:
        assert rule_id == 1
        assert limit == 5
        return [
            SavedRuleExecutionResultResponse(
                result_id=22,
                rule_id=1,
                rule_name="No active employee has negative salary",
                sql=(
                    "SELECT COUNT(*) AS violation_count FROM business_data.employees "
                    "WHERE status = 'active' AND salary < 0;"
                ),
                status="FAIL",
                observed_key="violation_count",
                observed_value=10,
                execution_time_ms=12,
                error_message=None,
                executed_at=datetime(2026, 5, 9, tzinfo=UTC),
            )
        ]

    monkeypatch.setattr(routes.registry, "get_rule", fake_get_rule)
    monkeypatch.setattr(routes.registry, "list_rule_results", fake_list_rule_results)

    response = client.get("/rules/1/results?limit=5")

    assert response.status_code == 200
    assert response.json()[0]["result_id"] == 22
    assert response.json()[0]["sql"].startswith("SELECT COUNT(*)")


def test_retrieve_all_results_includes_ad_hoc(monkeypatch) -> None:
    async def fake_list_all_results(limit: int) -> list[SavedRuleExecutionResultResponse]:
        assert limit == 10
        return [
            SavedRuleExecutionResultResponse(
                result_id=33,
                rule_id=None,
                rule_name="Negative salary check testing",
                sql="SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE salary < 0;",
                status="FAIL",
                observed_key="violation_count",
                observed_value=10,
                execution_time_ms=14,
                error_message=None,
                executed_at=datetime(2026, 5, 9, tzinfo=UTC),
            )
        ]

    monkeypatch.setattr(routes.registry, "list_all_results", fake_list_all_results)

    response = client.get("/results?limit=10")

    assert response.status_code == 200
    assert response.json()[0]["rule_id"] is None
    assert response.json()[0]["rule_name"] == "Negative salary check testing"


def test_preserves_ad_hoc_rules_run(monkeypatch) -> None:
    async def fake_execute_rule(rule) -> RuleExecutionResult:
        assert rule.rule_id is None
        return RuleExecutionResult(
            rule_id=None,
            rule_name=rule.rule_name,
            status="PASS",
            result={"observed_value": 1200},
            expected_result=rule.expected_result,
            execution_time_ms=8,
            executed_at=datetime(2026, 5, 9, tzinfo=UTC),
            error=None,
        )

    monkeypatch.setattr(routes.executor, "execute_rule", fake_execute_rule)

    response = client.post(
        "/rules/run",
        json={
            "rule_name": "At least 1000 students enrolled in 2026",
            "sql": "SELECT COUNT(*) AS observed_value FROM business_data.students;",
            "expected_result": {"type": "min_threshold", "value": 1000},
        },
    )

    assert response.status_code == 200
    assert response.json()["rule_id"] is None
    assert response.json()["status"] == "PASS"


def test_scheduler_rules_endpoint(monkeypatch) -> None:
    async def fake_list_scheduler_rule_statuses() -> list[SchedulerRuleStatusResponse]:
        return [
            SchedulerRuleStatusResponse(
                rule_id=1,
                rule_name="Scheduled rule",
                is_enabled=True,
                schedule_cron="*/5 * * * *",
                scheduler_status="schedulable",
            ),
            SchedulerRuleStatusResponse(
                rule_id=2,
                rule_name="Disabled rule",
                is_enabled=False,
                schedule_cron="*/5 * * * *",
                scheduler_status="disabled",
            ),
        ]

    monkeypatch.setattr(
        routes.registry,
        "list_scheduler_rule_statuses",
        fake_list_scheduler_rule_statuses,
    )

    response = client.get("/scheduler/rules")

    assert response.status_code == 200
    assert response.json()[0]["scheduler_status"] == "schedulable"
    assert response.json()[1]["scheduler_status"] == "disabled"
