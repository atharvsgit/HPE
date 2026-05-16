"""
tests/test_heuristic_engine.py
--------------------------------
Tests for the heuristic rule suggestion engine.
"""
import pytest

from app.platform.rule_intelligence.heuristic_engine import suggest_rules


TABLE = "business_data.employees"


def _make_profile(
    null_summary: dict,
    schema_info: dict,
    statistics: dict,
    uniqueness: dict,
    row_count: int = 1000,
) -> dict:
    return {
        "table_name": TABLE,
        "row_count": row_count,
        "column_count": len(null_summary),
        "null_summary": null_summary,
        "schema_info": schema_info,
        "statistics": statistics,
        "uniqueness": uniqueness,
    }


class TestHeuristicEngine:
    def test_not_null_rule_generated_for_zero_null_column(self):
        profile = _make_profile(
            null_summary={"id": 0.0},
            schema_info={"id": "integer"},
            statistics={"id": {"min": 1, "max": 1000}},
            uniqueness={"id": {"unique_pct": 100.0, "unique_count": 1000, "is_unique": True}},
        )
        suggestions = suggest_rules(profile, TABLE)
        rule_names = [s["suggested_rule_name"] for s in suggestions]
        # Should suggest a null check for zero-null column
        assert any("null" in n.lower() for n in rule_names)

    def test_uniqueness_rule_for_key_column(self):
        profile = _make_profile(
            null_summary={"employee_id": 0.0},
            schema_info={"employee_id": "integer"},
            statistics={"employee_id": {"min": 1, "max": 1000}},
            uniqueness={"employee_id": {"unique_pct": 100.0, "unique_count": 1000, "is_unique": True}},
        )
        suggestions = suggest_rules(profile, TABLE)
        sql_list = [s["suggested_sql"] for s in suggestions]
        assert any("DISTINCT" in sql for sql in sql_list)

    def test_range_check_for_numeric_column(self):
        profile = _make_profile(
            null_summary={"salary": 0.0},
            schema_info={"salary": "float"},
            statistics={"salary": {"min": 1000.0, "max": 500000.0}},
            uniqueness={"salary": {"unique_pct": 90.0, "unique_count": 900, "is_unique": False}},
        )
        suggestions = suggest_rules(profile, TABLE)
        sql_list = [s["suggested_sql"] for s in suggestions]
        assert any("< 1000.0" in sql or "> 500000.0" in sql for sql in sql_list)

    def test_category_check_for_low_cardinality_string(self):
        profile = _make_profile(
            null_summary={"status": 0.0},
            schema_info={"status": "string"},
            statistics={"status": {
                "top_values": [
                    {"value": "active", "count": 800},
                    {"value": "inactive", "count": 200},
                ]
            }},
            uniqueness={"status": {"unique_pct": 0.2, "unique_count": 2, "is_unique": False}},
        )
        suggestions = suggest_rules(profile, TABLE)
        sql_list = [s["suggested_sql"] for s in suggestions]
        assert any("NOT IN" in sql for sql in sql_list)

    def test_null_threshold_suggestion_for_low_null_column(self):
        profile = _make_profile(
            null_summary={"phone": 3.0},  # 3% null
            schema_info={"phone": "string"},
            statistics={"phone": {}},
            uniqueness={"phone": {"unique_pct": 80.0, "unique_count": 800, "is_unique": False}},
        )
        suggestions = suggest_rules(profile, TABLE)
        threshold_suggestions = [
            s for s in suggestions if s["expected_result_type"] == "max_threshold"
        ]
        assert len(threshold_suggestions) > 0

    def test_suggestion_has_all_required_fields(self):
        profile = _make_profile(
            null_summary={"col": 0.0},
            schema_info={"col": "integer"},
            statistics={"col": {"min": 0, "max": 100}},
            uniqueness={"col": {"unique_pct": 100.0, "unique_count": 1000, "is_unique": True}},
        )
        suggestions = suggest_rules(profile, TABLE)
        assert len(suggestions) > 0
        for s in suggestions:
            assert "column_name" in s
            assert "suggested_sql" in s
            assert "expected_result_type" in s
            assert "confidence" in s
            assert 0.0 <= s["confidence"] <= 1.0

    def test_empty_profile_returns_no_suggestions(self):
        profile = _make_profile(
            null_summary={},
            schema_info={},
            statistics={},
            uniqueness={},
        )
        suggestions = suggest_rules(profile, TABLE)
        assert suggestions == []
