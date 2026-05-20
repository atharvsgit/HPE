"""
tests/test_parquet_writer.py
============================
Unit tests for the enterprise parquet writer service.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from app.ingestion.writers.parquet_writer import ParquetWriter, ParquetWriterError


@pytest.fixture
def dummy_df():
    return pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})


class TestParquetWriter:
    
    def test_parquet_writer_initialization(self, tmp_path):
        writer = ParquetWriter(base_output_dir=tmp_path, schema_version="v1")
        assert writer.base_output_dir == tmp_path
        assert writer.schema_version == "v1"

    @patch("polars.DataFrame.write_parquet")
    def test_write_creates_partitioned_directory(self, mock_write, dummy_df, tmp_path):
        writer = ParquetWriter(base_output_dir=tmp_path)
        batch_id = "batch_test123"
        
        # Test atomic write replacement logic by skipping actual polars IO
        # We need to simulate the file creation so atomic rename doesn't fail
        def mock_write_parquet_effect(file_path, **kwargs):
            Path(file_path).touch()
            
        mock_write.side_effect = mock_write_parquet_effect
        
        result_path = writer.write(
            df=dummy_df,
            dataset_name="test_dataset",
            batch_id=batch_id,
            partition_date="2026-05-15"
        )
        
        # Verify result path
        expected_dir = tmp_path / "test_dataset" / "partition_date=2026-05-15"
        assert expected_dir.exists()
        
        expected_file = expected_dir / f"{batch_id}.parquet"
        assert result_path == expected_file
        assert result_path.exists()
        
        # Check compression args passed to pyarrow
        mock_write.assert_called_once()
        _, kwargs = mock_write.call_args
        assert kwargs.get("compression") == "snappy"
        assert kwargs.get("use_pyarrow") is True

    @patch("polars.DataFrame.write_parquet")
    def test_success_marker_created(self, mock_write, dummy_df, tmp_path):
        writer = ParquetWriter(base_output_dir=tmp_path, schema_version="v1")
        batch_id = "batch_test_marker"
        
        def mock_write_parquet_effect(file_path, **kwargs):
            Path(file_path).touch()
            
        mock_write.side_effect = mock_write_parquet_effect
        
        writer.write(
            df=dummy_df,
            dataset_name="test_dataset",
            batch_id=batch_id,
            partition_date="2026-05-15"
        )
        
        # Check marker file
        marker_file = tmp_path / "test_dataset" / "partition_date=2026-05-15" / f"_SUCCESS_{batch_id}"
        assert marker_file.exists()
        
        with open(marker_file, "r") as f:
            metadata = json.load(f)
            
        assert metadata["batch_id"] == batch_id
        assert metadata["row_count"] == 3
        assert "completed_at" in metadata
        assert metadata["schema_version"] == "v1"

    @patch("polars.DataFrame.write_parquet")
    def test_write_failure_raises_parquet_writer_error(self, mock_write, dummy_df, tmp_path):
        writer = ParquetWriter(base_output_dir=tmp_path)
        
        # Force a failure during write
        mock_write.side_effect = Exception("Simulated disk error")
        
        with pytest.raises(ParquetWriterError) as exc_info:
            writer.write(
                df=dummy_df,
                dataset_name="fail_dataset",
                batch_id="batch_fail",
                partition_date="2026-05-15"
            )
            
        assert "Parquet write operation failed: Simulated disk error" in str(exc_info.value)
