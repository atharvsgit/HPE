from decimal import Decimal

from app.daemon.rule_identity import build_rule_fingerprint


def test_rule_fingerprint_normalizes_equivalent_sql_and_decimal_values() -> None:
    first = build_rule_fingerprint(
        database_connection_id=1,
        sql="select count(*) as violation_count from business_data.employees where salary < 0;",
        expected_result_type="max_threshold",
        expected_result_value=Decimal("1.0"),
    )
    second = build_rule_fingerprint(
        database_connection_id=1,
        sql="""
            SELECT COUNT(*) AS violation_count
            FROM business_data.employees
            WHERE salary < 0
        """,
        expected_result_type="max_threshold",
        expected_result_value=Decimal("1.00"),
    )

    assert first == second


def test_rule_fingerprint_keeps_different_database_targets_distinct() -> None:
    sql = "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE salary < 0"

    first = build_rule_fingerprint(
        database_connection_id=1,
        sql=sql,
        expected_result_type="zero_violations",
        expected_result_value=None,
    )
    second = build_rule_fingerprint(
        database_connection_id=2,
        sql=sql,
        expected_result_type="zero_violations",
        expected_result_value=None,
    )

    assert first != second
