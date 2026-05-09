import pytest

from app.daemon.sql_safety import SQLSafetyError, strip_trailing_semicolon, validate_safe_select


def test_accepts_single_select() -> None:
    validate_safe_select(
        "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE status = 'active';"
    )


def test_rejects_multiple_statements() -> None:
    with pytest.raises(SQLSafetyError):
        validate_safe_select("SELECT COUNT(*) AS observed_value FROM business_data.employees; SELECT 1;")


def test_rejects_non_select() -> None:
    with pytest.raises(SQLSafetyError):
        validate_safe_select("UPDATE business_data.employees SET salary = 1;")


def test_rejects_dangerous_keywords_even_inside_select() -> None:
    with pytest.raises(SQLSafetyError):
        validate_safe_select("SELECT COUNT(*) AS observed_value FROM business_data.employees DROP TABLE x;")


def test_ignores_dangerous_words_inside_string_literals() -> None:
    validate_safe_select(
        "SELECT COUNT(*) AS observed_value FROM business_data.employees WHERE full_name = 'DROP';"
    )


def test_rejects_unsafe_functions() -> None:
    with pytest.raises(SQLSafetyError):
        validate_safe_select("SELECT pg_sleep(1) AS observed_value;")


def test_strip_trailing_semicolon() -> None:
    assert strip_trailing_semicolon("SELECT 1;") == "SELECT 1"
