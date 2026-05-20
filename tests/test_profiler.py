"""
Combined profiling tests for ingestion profiling and Platform Intelligence profiling utilities.
"""

import json
from datetime import date

import polars as pl
import pytest

from app.ingestion.profiling.profiler import DatasetProfiler, run_profiler
from app.platform.profiling.distribution_analyzer import analyze_distributions
from app.platform.profiling.null_analyzer import analyze_nulls
from app.platform.profiling.schema_analyzer import analyze_schema
from app.platform.profiling.statistics_generator import generate_statistics
from app.platform.profiling.uniqueness_analyzer import analyze_uniqueness


def test_ingestion_profiler_initialization():
    profiler = DatasetProfiler("test_dataset", "/tmp/profiling")
    assert profiler.dataset_name == "test_dataset"
    assert "test_dataset" in str(profiler.output_dir)
    assert "latest" in str(profiler.output_dir)


def test_ingestion_profiler_empty_dataframe():
    df = pl.DataFrame({"a": [], "b": []})
    profiler = DatasetProfiler("empty_dataset", "/tmp/profiling")

    result = profiler.profile(df)

    assert result["dataset_name"] == "empty_dataset"
    assert result["row_count"] == 0
    assert result["column_count"] == 2
    assert len(result["columns"]) == 0


def test_ingestion_profiler_basic_metrics(tmp_path):
    df = pl.DataFrame(
        {
            "id": [1, 2, 3, 4, None],
            "name": ["A", "B", "A", "C", "A"],
            "join_date": [
                date(2023, 1, 1),
                date(2023, 1, 2),
                date(2023, 1, 3),
                date(2023, 1, 4),
                date(2023, 1, 5),
            ],
        }
    )

    result = run_profiler("metric_test", df, output_base_dir=str(tmp_path))

    assert result["row_count"] == 5
    assert result["column_count"] == 3

    col_id = result["columns"]["id"]
    assert col_id["null_count"] == 1
    assert col_id["unique_count"] == 5
    assert col_id["min"] == 1
    assert col_id["max"] == 4
    assert col_id["percentiles"]["50"] in (2.5, 3.0)
    assert "Int" in col_id["inferred_data_type"]

    col_str = result["columns"]["name"]
    assert "A" in col_str["top_values"]
    assert col_str["top_values"]["A"] == 3
    assert "String" in col_str["inferred_data_type"]

    col_date = result["columns"]["join_date"]
    assert col_date["min"] == "2023-01-01"
    assert "Date" in col_date["inferred_data_type"]


def test_ingestion_profiler_saves_file(tmp_path):
    df = pl.DataFrame({"x": [1, 2, 3]})
    profiler = DatasetProfiler("save_test", str(tmp_path))

    result = profiler.profile(df)
    saved_path = profiler.save_profile(result)

    assert saved_path.exists()
    assert saved_path.name == "profile.json"

    with open(saved_path) as file_obj:
        loaded = json.load(file_obj)
        assert loaded["row_count"] == 3


@pytest.fixture
def sample_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "employee_id": [1, 2, 3, 4, 5],
            "name": ["Alice", "Bob", "Carol", None, "Dave"],
            "salary": [50000.0, 75000.0, None, 60000.0, 90000.0],
            "department": ["HR", "Eng", "Eng", "HR", "Eng"],
            "active": [True, True, False, True, False],
        }
    )


class TestPlatformNullAnalyzer:
    def test_null_percentages(self, sample_df):
        result = analyze_nulls(sample_df)
        assert result["employee_id"] == 0.0
        assert result["name"] == 20.0
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


class TestPlatformSchemaAnalyzer:
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


class TestPlatformDistributionAnalyzer:
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


class TestPlatformUniquenessAnalyzer:
    def test_unique_id_column(self, sample_df):
        result = analyze_uniqueness(sample_df)
        assert result["employee_id"]["unique_pct"] == 100.0
        assert result["employee_id"]["is_unique"] is True

    def test_non_unique_column(self, sample_df):
        result = analyze_uniqueness(sample_df)
        assert result["department"]["unique_pct"] < 100.0
        assert result["department"]["is_unique"] is False

    def test_unique_count(self, sample_df):
        result = analyze_uniqueness(sample_df)
        assert result["department"]["unique_count"] == 2


class TestPlatformStatisticsGenerator:
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
