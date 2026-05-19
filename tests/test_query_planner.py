"""
tests/test_query_planner.py
----------------------------
Tests for the SQLGlot-based query planner.
"""

import pytest

from app.platform.rule_intelligence.query_planner import (
    QueryPlannerError,
    compile_rule_to_sql,
    extract_table_names,
    validate_and_optimize,
)


class TestValidateAndOptimize:
    def test_valid_violation_count_sql(self):
        sql = "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE salary < 0"
        result = validate_and_optimize(sql)
        assert "violation_count" in result
        assert "SELECT" in result.upper()

    def test_valid_observed_value_sql(self):
        sql = "SELECT COUNT(*) AS observed_value FROM business_data.employees"
        result = validate_and_optimize(sql)
        assert "observed_value" in result

    def test_rejects_invalid_output_column_name(self):
        sql = "SELECT COUNT(*) AS bad_column_name FROM business_data.employees"
        with pytest.raises(QueryPlannerError, match="violation_count|observed_value"):
            validate_and_optimize(sql)

    def test_rejects_multiple_output_columns(self):
        sql = "SELECT id, salary FROM business_data.employees"
        with pytest.raises(QueryPlannerError, match="one output column"):
            validate_and_optimize(sql)

    def test_rejects_non_select_statement(self):
        sql = "DELETE FROM business_data.employees WHERE id = 1"
        with pytest.raises(QueryPlannerError):
            validate_and_optimize(sql)

    def test_rejects_empty_sql(self):
        with pytest.raises(QueryPlannerError):
            validate_and_optimize("")

    def test_rejects_multiple_statements(self):
        sql = (
            "SELECT COUNT(*) AS violation_count FROM t; "
            "SELECT COUNT(*) AS violation_count FROM t"
        )
        with pytest.raises(QueryPlannerError, match="single"):
            validate_and_optimize(sql)

    def test_allowed_table_passes(self):
        sql = "SELECT COUNT(*) AS violation_count FROM business_data.employees"
        result = validate_and_optimize(sql, allowed_tables={"business_data.employees"})
        assert "business_data" in result

    def test_allowed_table_rejects_other_table(self):
        sql = "SELECT COUNT(*) AS violation_count FROM business_data.students"
        with pytest.raises(QueryPlannerError, match="outside the allowed"):
            validate_and_optimize(sql, allowed_tables={"business_data.employees"})

    def test_extract_table_names(self):
        sql = "SELECT COUNT(*) AS violation_count FROM business_data.employees"
        assert extract_table_names(sql) == {"business_data.employees"}


class TestCompileRuleToSql:
    def test_null_check(self):
        sql = compile_rule_to_sql(
            {
                "table": "business_data.employees",
                "column": "salary",
                "rule_type": "null_check",
            }
        )
        assert "IS NULL" in sql
        assert "violation_count" in sql

    def test_uniqueness_check(self):
        sql = compile_rule_to_sql(
            {
                "table": "business_data.employees",
                "column": "employee_id",
                "rule_type": "uniqueness_check",
            }
        )
        assert "DISTINCT" in sql
        assert "violation_count" in sql

    def test_min_value_check(self):
        sql = compile_rule_to_sql(
            {
                "table": "business_data.employees",
                "column": "salary",
                "rule_type": "min_value",
                "min_value": 0,
            }
        )
        assert "< 0" in sql
        assert "violation_count" in sql

    def test_max_value_check(self):
        sql = compile_rule_to_sql(
            {
                "table": "business_data.employees",
                "column": "salary",
                "rule_type": "max_value",
                "max_value": 1000000,
            }
        )
        assert "> 1000000" in sql

    def test_range_check(self):
        sql = compile_rule_to_sql(
            {
                "table": "business_data.employees",
                "column": "age",
                "rule_type": "range_check",
                "min_value": 18,
                "max_value": 65,
            }
        )
        assert "< 18" in sql
        assert "> 65" in sql

    def test_missing_table_raises(self):
        with pytest.raises(QueryPlannerError, match="table"):
            compile_rule_to_sql({"column": "salary", "rule_type": "null_check"})

    def test_missing_required_param_raises(self):
        with pytest.raises(QueryPlannerError, match="min_value"):
            compile_rule_to_sql({"table": "t", "column": "c", "rule_type": "min_value"})

    def test_unsupported_rule_type_raises(self):
        with pytest.raises(QueryPlannerError, match="Unsupported"):
            compile_rule_to_sql(
                {"table": "t", "column": "c", "rule_type": "unknown_type"}
            )
