"""
tests/test_profiler.py
-----------------------
Tests for the data profiling sub-modules.
Uses in-memory Polars DataFrames — no database connection required.
"""
import pytest
import polars as pl

from app.platform.profiling.null_analyzer import analyze_nulls
from app.platform.profiling.schema_analyzer import analyze_schema
from app.platform.profiling.distribution_analyzer import analyze_distributions
from app.platform.profiling.uniqueness_analyzer import analyze_uniqueness
from app.platform.profiling.statistics_generator import generate_statistics


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame({
        "employee_id": [1, 2, 3, 4, 5],
        "name":        ["Alice", "Bob", "Carol", None, "Dave"],
        "salary":      [50000.0, 75000.0, None, 60000.0, 90000.0],
        "department":  ["HR", "Eng", "Eng", "HR", "Eng"],
        "active":      [True, True, False, True, False],
    })


class TestNullAnalyzer:
    def test_null_percentages(self, sample_df):
        result = analyze_nulls(sample_df)
        assert result["employee_id"] == 0.0
        assert result["name"] == 20.0   # 1/5 = 20%
        assert result["salary"] == 20.0

    def test_no_nulls(self):
        df = pl.DataFrame({"a": [1, 2, 3]})
        result = analyze_nulls(df)
        assert result["a"] == 0.0

    def test_all_nulls(self):
        df = pl.DataFrame({"a": [None, None, None]}, schema={"a": pl.Int64})
        result = analyze_nulls(df)
        assert result["a"] == 100.0

    def test_empty_dataframe(self):
        df = pl.DataFrame({"a": []}, schema={"a": pl.Int64})
        result = analyze_nulls(df)
        assert result["a"] == 0.0


class TestSchemaAnalyzer:
    def test_integer_columns(self, sample_df):
        result = analyze_schema(sample_df)
        assert result["employee_id"] == "integer"

    def test_string_columns(self, sample_df):
        result = analyze_schema(sample_df)
        assert result["name"] == "string"

    def test_float_columns(self, sample_df):
        result = analyze_schema(sample_df)
        assert result["salary"] == "float"

    def test_boolean_columns(self, sample_df):
        result = analyze_schema(sample_df)
        assert result["active"] == "boolean"


class TestDistributionAnalyzer:
    def test_numeric_stats(self, sample_df):
        result = analyze_distributions(sample_df)
        salary_stats = result["salary"]
        assert "min" in salary_stats
        assert "max" in salary_stats
        assert "mean" in salary_stats

    def test_string_top_values(self, sample_df):
        result = analyze_distributions(sample_df)
        dept_stats = result["department"]
        assert "top_values" in dept_stats
        assert len(dept_stats["top_values"]) > 0

    def test_numeric_min_max(self, sample_df):
        result = analyze_distributions(sample_df)
        assert result["salary"]["min"] == 50000.0
        assert result["salary"]["max"] == 90000.0


class TestUniquenessAnalyzer:
    def test_unique_id_column(self, sample_df):
        result = analyze_uniqueness(sample_df)
        assert result["employee_id"]["unique_pct"] == 100.0
        assert result["employee_id"]["is_unique"] is True

    def test_non_unique_column(self, sample_df):
        result = analyze_uniqueness(sample_df)
        # "department" has only "HR" and "Eng" — not all rows unique
        assert result["department"]["unique_pct"] < 100.0
        assert result["department"]["is_unique"] is False

    def test_unique_count(self, sample_df):
        result = analyze_uniqueness(sample_df)
        assert result["department"]["unique_count"] == 2


class TestStatisticsGenerator:
    def test_full_profile_structure(self, sample_df):
        profile = generate_statistics(sample_df, "test.employees")
        assert profile["table_name"] == "test.employees"
        assert profile["row_count"] == 5
        assert profile["column_count"] == 5
        assert "null_summary" in profile
        assert "schema_info" in profile
        assert "statistics" in profile
        assert "uniqueness" in profile
        assert "profiled_at" in profile

    def test_profile_all_columns_present(self, sample_df):
        profile = generate_statistics(sample_df, "test.t")
        expected_cols = {"employee_id", "name", "salary", "department", "active"}
        assert set(profile["null_summary"].keys()) == expected_cols
        assert set(profile["schema_info"].keys()) == expected_cols
