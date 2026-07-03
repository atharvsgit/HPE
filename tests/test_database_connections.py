from app.models.product import DatabaseConnectionCreate
from app.services.database_identity import build_database_connection_fingerprint


def _connection(**overrides) -> DatabaseConnectionCreate:
    payload = {
        "name": "Docker Demo Postgres",
        "db_type": "postgresql",
        "host": "postgres",
        "port": 5432,
        "database": "dq_test",
        "username": "dq_executor",
        "password": "dq_executor_password",
    }
    payload.update(overrides)
    return DatabaseConnectionCreate(**payload)


def test_connection_fingerprint_ignores_display_name_password_and_case() -> None:
    first = _connection(name="Primary", password="one")
    second = _connection(name="Renamed", host=" POSTGRES ", username="DQ_EXECUTOR", password="two")

    assert build_database_connection_fingerprint(first) == build_database_connection_fingerprint(second)


def test_connection_fingerprint_keeps_different_users_distinct() -> None:
    first = _connection(username="dq_executor")
    second = _connection(username="reporting_user")

    assert build_database_connection_fingerprint(first) != build_database_connection_fingerprint(second)
