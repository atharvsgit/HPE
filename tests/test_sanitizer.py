"""
tests/test_sanitizer.py
-----------------------
Tests for the Platform Intelligence rule suggestion sanitizer.
"""

from app.platform.rule_intelligence.sanitizer import sanitize_suggestions


def _suggestion(**overrides):
    base = {
        "table_name": "business_data.employees",
        "column_name": "salary",
        "suggestion_type": "heuristic",
        "suggested_rule_name": "salary must be non-negative",
        "suggested_sql": (
            "SELECT COUNT(*) AS violation_count "
            "FROM business_data.employees WHERE salary < 0"
        ),
        "expected_result_type": "zero_violations",
        "expected_result_value": None,
        "confidence": 1.5,
    }
    base.update(overrides)
    return base


def test_sanitizer_accepts_safe_suggestion_and_clamps_confidence():
    accepted, rejected = sanitize_suggestions(
        [_suggestion()],
        "business_data.employees",
    )

    assert rejected == []
    assert len(accepted) == 1
    assert accepted[0]["confidence"] == 1.0
    assert "violation_count" in accepted[0]["suggested_sql"]


def test_sanitizer_rejects_wrong_table():
    accepted, rejected = sanitize_suggestions(
        [_suggestion(table_name="business_data.students")],
        "business_data.employees",
    )

    assert accepted == []
    assert len(rejected) == 1
    assert "expected 'business_data.employees'" in rejected[0].reason


def test_sanitizer_rejects_unsafe_sql():
    accepted, rejected = sanitize_suggestions(
        [_suggestion(suggested_sql="DELETE FROM business_data.employees")],
        "business_data.employees",
    )

    assert accepted == []
    assert len(rejected) == 1
    assert (
        "Only single-statement SELECT" in rejected[0].reason
        or "Only" in rejected[0].reason
    )
