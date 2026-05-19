from datetime import date
from pathlib import Path
import os
import json

import polars as pl
import pytest

from app.ingestion.profiling.profiler import DatasetProfiler, run_profiler

def test_profiler_initialization():
    profiler = DatasetProfiler("test_dataset", "/tmp/profiling")
    assert profiler.dataset_name == "test_dataset"
    assert "test_dataset" in str(profiler.output_dir)
    assert "latest" in str(profiler.output_dir)

def test_profiler_empty_dataframe():
    df = pl.DataFrame({"a": [], "b": []})
    profiler = DatasetProfiler("empty_dataset", "/tmp/profiling")
    
    result = profiler.profile(df)
    
    assert result["dataset_name"] == "empty_dataset"
    assert result["row_count"] == 0
    assert result["column_count"] == 2
    assert len(result["columns"]) == 0

def test_profiler_basic_metrics(tmp_path):
    df = pl.DataFrame({
        "id": [1, 2, 3, 4, None],
        "name": ["A", "B", "A", "C", "A"],
        "join_date": [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5)]
    })
    
    result = run_profiler("metric_test", df, output_base_dir=str(tmp_path))
    
    # Global
    assert result["row_count"] == 5
    assert result["column_count"] == 3
    
    # Numeric column checks
    col_id = result["columns"]["id"]
    assert col_id["null_count"] == 1
    assert col_id["unique_count"] == 5  # 4 ints + 1 null 
    assert col_id["min"] == 1
    assert col_id["max"] == 4
    assert col_id["percentiles"]["50"] in (2.5, 3.0)  # Polars interpolation modes can return either depending on version
    assert "Int" in col_id["inferred_data_type"]
    
    # String column checks
    col_str = result["columns"]["name"]
    assert "A" in col_str["top_values"]
    assert col_str["top_values"]["A"] == 3
    assert "String" in col_str["inferred_data_type"]
    
    # Date column checks
    col_date = result["columns"]["join_date"]
    assert col_date["min"] == "2023-01-01"
    assert "Date" in col_date["inferred_data_type"]

def test_profiler_saves_file(tmp_path):
    df = pl.DataFrame({"x": [1, 2, 3]})
    profiler = DatasetProfiler("save_test", str(tmp_path))
    
    result = profiler.profile(df)
    saved_path = profiler.save_profile(result)
    
    assert saved_path.exists()
    assert saved_path.name == "profile.json"
    
    with open(saved_path, "r") as f:
        loaded = json.load(f)
        assert loaded["row_count"] == 3
