"""
tests/test_ingestion_service.py
================================
Unit tests for app/ingestion/services/ingestion_service.py.

Strategy
--------
- All external I/O (CSV read, Parquet write, profiler, contract, marker) is
  patched so tests are fast, hermetic, and require no filesystem fixtures.
- The happy-path test uses a real temp CSV to verify end-to-end wiring.
- Each error test patches exactly one stage to raise its domain exception and
  asserts that IngestionServiceError is raised with the correct ``stage``.
"""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from app.ingestion.services.ingestion_service import (
    IngestionPipelineConfig,
    IngestionServiceError,
    PipelineResult,
    _stage_1_load_csv,
    _stage_3_4_enrich_metadata,
    _stage_5_detect_duplicates,
    _stage_6_write_parquet,
    _stage_7_profile_dataset,
    _stage_8_generate_contract,
    _stage_9_write_success_marker,
    run_ingestion_pipeline,
)
from app.ingestion.connectors.csv_connector import CSVConnectorConfig
from app.ingestion.processors.duplicate_detector import DuplicateDetectionError
from app.ingestion.utils.metadata import MetadataEnrichmentError
from app.ingestion.writers.parquet_writer import ParquetWriterError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    """Write a minimal CSV file and return its Path."""
    p = tmp_path / "employees.csv"
    p.write_text(
        "EmployeeID,First Name,Salary,Department\n"
        "1,Alice,70000,Engineering\n"
        "2,Bob,80000,Marketing\n"
        "1,Alice,70000,Engineering\n",  # duplicate of row 0
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def minimal_df() -> pl.DataFrame:
    """A tiny enriched-like DataFrame for stage unit tests."""
    return pl.DataFrame({
        "employee_id": [1, 2, 3],
        "first_name": ["Alice", "Bob", "Carol"],
        "salary": [70_000, 80_000, 90_000],
        "__batch_id": ["b_001"] * 3,
        "__row_hash": ["aaa", "bbb", "ccc"],
        "__is_duplicate": [False, False, False],
    })


@pytest.fixture()
def pipeline_config(tmp_path: Path) -> IngestionPipelineConfig:
    """Config pointing all output dirs to tmp_path."""
    return IngestionPipelineConfig(
        storage_dir=tmp_path / "lake",
        profiling_dir=tmp_path / "profiles",
        contracts_dir=tmp_path / "contracts",
    )


# ---------------------------------------------------------------------------
# PipelineResult unit tests
# ---------------------------------------------------------------------------

class TestPipelineResult:
    def test_to_dict_contains_required_keys(self):
        result = PipelineResult(
            status="success",
            batch_id="batch_abc123",
            dataset_name="sales",
            row_count=100,
            parquet_path="/data/lake/sales/p.parquet",
            profile_path="/data/profiles/p.json",
            contract_path="/data/contracts/c.json",
            ready_for_validation=True,
        )
        d = result.to_dict()
        required = {
            "status", "batch_id", "dataset_name", "row_count",
            "parquet_path", "profile_path", "contract_path",
            "ready_for_validation", "duplicate_count",
            "execution_time_ms", "stage_timings",
        }
        assert required == set(d.keys())

    def test_ready_for_validation_true_on_success(self):
        result = PipelineResult(
            status="success", batch_id="b", dataset_name="d",
            row_count=1, parquet_path="p", profile_path="pr",
            contract_path="c", ready_for_validation=True,
        )
        assert result.ready_for_validation is True

    def test_frozen_dataclass_is_immutable(self):
        result = PipelineResult(
            status="success", batch_id="b", dataset_name="d",
            row_count=1, parquet_path="p", profile_path="pr",
            contract_path="c", ready_for_validation=True,
        )
        with pytest.raises((AttributeError, TypeError)):
            result.status = "fail"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IngestionServiceError unit tests
# ---------------------------------------------------------------------------

class TestIngestionServiceError:
    def test_stage_attribute_is_set(self):
        exc = IngestionServiceError("csv_load", "file not found")
        assert exc.stage == "csv_load"

    def test_str_includes_stage_and_message(self):
        exc = IngestionServiceError("parquet_write", "disk full")
        assert "parquet_write" in str(exc)
        assert "disk full" in str(exc)

    def test_cause_is_chained(self):
        cause = RuntimeError("underlying io error")
        exc = IngestionServiceError("profiling", "profiler failed", cause)
        assert exc.__cause__ is cause


# ---------------------------------------------------------------------------
# Stage 1+2: CSV load
# ---------------------------------------------------------------------------

class TestStage1LoadCSV:
    def test_returns_dataframe(self, sample_csv, pipeline_config):
        df = _stage_1_load_csv(sample_csv, pipeline_config)
        assert isinstance(df, pl.DataFrame)
        assert df.height == 3

    def test_columns_are_snake_case(self, sample_csv, pipeline_config):
        df = _stage_1_load_csv(sample_csv, pipeline_config)
        for col in df.columns:
            assert col == col.lower()
            assert " " not in col

    def test_missing_file_raises_ingestion_error(self, tmp_path, pipeline_config):
        with pytest.raises(IngestionServiceError) as exc_info:
            _stage_1_load_csv(tmp_path / "ghost.csv", pipeline_config)
        assert exc_info.value.stage == "csv_load"

    def test_empty_file_raises_ingestion_error(self, tmp_path, pipeline_config):
        empty = tmp_path / "empty.csv"
        empty.write_text("")
        with pytest.raises(IngestionServiceError) as exc_info:
            _stage_1_load_csv(empty, pipeline_config)
        assert exc_info.value.stage == "csv_load"


# ---------------------------------------------------------------------------
# Stage 3+4: Metadata enrichment
# ---------------------------------------------------------------------------

class TestStage34Enrichment:
    def test_adds_metadata_columns(self, sample_csv, pipeline_config):
        df = _stage_1_load_csv(sample_csv, pipeline_config)
        enriched = _stage_3_4_enrich_metadata(df, "batch_001", "employees")
        meta_cols = {"__batch_id", "__ingested_at", "__row_hash", "__is_duplicate", "__record_id"}
        assert meta_cols.issubset(set(enriched.columns))

    def test_batch_id_propagated(self, sample_csv, pipeline_config):
        df = _stage_1_load_csv(sample_csv, pipeline_config)
        enriched = _stage_3_4_enrich_metadata(df, "batch_xyz", "employees")
        assert enriched["__batch_id"].unique().to_list() == ["batch_xyz"]

    def test_enrichment_error_raises_ingestion_error(self, sample_csv, pipeline_config):
        df = _stage_1_load_csv(sample_csv, pipeline_config)
        with patch(
            "app.ingestion.services.ingestion_service.MetadataEnricher.enrich",
            side_effect=MetadataEnrichmentError("boom"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                _stage_3_4_enrich_metadata(df, "b", "d")
            assert exc_info.value.stage == "metadata_enrichment"


# ---------------------------------------------------------------------------
# Stage 5: Duplicate detection
# ---------------------------------------------------------------------------

class TestStage5DuplicateDetection:
    def test_returns_df_and_count(self, minimal_df):
        df_out, dup_count = _stage_5_detect_duplicates(minimal_df, subset=None)
        assert isinstance(df_out, pl.DataFrame)
        assert isinstance(dup_count, int)

    def test_detects_zero_duplicates_in_unique_data(self, minimal_df):
        _, dup_count = _stage_5_detect_duplicates(minimal_df, subset=None)
        assert dup_count == 0

    def test_detects_duplicates_in_repeated_rows(self):
        df = pl.DataFrame({
            "a": [1, 2, 1],
            "b": ["x", "y", "x"],
        })
        _, dup_count = _stage_5_detect_duplicates(df, subset=None)
        assert dup_count == 2  # both rows matching a=1,b=x are flagged

    def test_subset_limits_hashing_columns(self):
        # Rows differ only in column 'c'; subset=['a','b'] → they look like dupes
        df = pl.DataFrame({
            "a": [1, 1],
            "b": ["x", "x"],
            "c": ["alpha", "beta"],
        })
        _, dup_count = _stage_5_detect_duplicates(df, subset=["a", "b"])
        assert dup_count == 2

    def test_detection_error_raises_ingestion_error(self, minimal_df):
        with patch(
            "app.ingestion.services.ingestion_service.DuplicateDetector.process",
            side_effect=DuplicateDetectionError("hash failure"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                _stage_5_detect_duplicates(minimal_df, subset=None)
            assert exc_info.value.stage == "duplicate_detection"


# ---------------------------------------------------------------------------
# Stage 6: Parquet write
# ---------------------------------------------------------------------------

class TestStage6ParquetWrite:
    def _fake_parquet_path(self, config: IngestionPipelineConfig, dataset: str, batch: str, date: str) -> Path:
        """Build the expected parquet path without actually writing."""
        p = config.storage_dir / dataset / f"partition_date={date}" / f"{batch}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()  # create empty file as stand-in
        return p

    def test_returns_path(self, minimal_df, pipeline_config):
        expected = self._fake_parquet_path(pipeline_config, "employees", "batch_001", "2026-05-15")
        with patch(
            "app.ingestion.services.ingestion_service.ParquetWriter.write",
            return_value=expected,
        ):
            path = _stage_6_write_parquet(
                minimal_df, "employees", "batch_001", "2026-05-15", pipeline_config
            )
        assert isinstance(path, Path)
        assert path == expected

    def test_parquet_path_contains_dataset_and_partition(self, minimal_df, pipeline_config):
        expected = self._fake_parquet_path(pipeline_config, "sales", "batch_001", "2026-05-15")
        with patch(
            "app.ingestion.services.ingestion_service.ParquetWriter.write",
            return_value=expected,
        ):
            path = _stage_6_write_parquet(
                minimal_df, "sales", "batch_001", "2026-05-15", pipeline_config
            )
        assert "sales" in str(path)
        assert "2026-05-15" in str(path)

    def test_write_error_raises_ingestion_error(self, minimal_df, pipeline_config):
        with patch(
            "app.ingestion.services.ingestion_service.ParquetWriter.write",
            side_effect=ParquetWriterError("disk full"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                _stage_6_write_parquet(minimal_df, "d", "b", "2026-01-01", pipeline_config)
            assert exc_info.value.stage == "parquet_write"


# ---------------------------------------------------------------------------
# Stage 7: Profiling
# ---------------------------------------------------------------------------

class TestStage7Profiling:
    def test_returns_path_and_dict(self, minimal_df, pipeline_config):
        path, profile = _stage_7_profile_dataset(
            minimal_df, "employees", "batch_001", pipeline_config
        )
        assert isinstance(path, Path)
        assert path.exists()
        assert isinstance(profile, dict)
        assert "columns" in profile

    def test_profile_contains_row_count(self, minimal_df, pipeline_config):
        _, profile = _stage_7_profile_dataset(
            minimal_df, "employees", "batch_001", pipeline_config
        )
        assert profile["row_count"] == minimal_df.height

    def test_profiling_error_raises_ingestion_error(self, minimal_df, pipeline_config):
        with patch(
            "app.ingestion.services.ingestion_service.DatasetProfiler.profile",
            side_effect=RuntimeError("oom"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                _stage_7_profile_dataset(minimal_df, "d", "b", pipeline_config)
            assert exc_info.value.stage == "profiling"


# ---------------------------------------------------------------------------
# Stage 8: Contract generation
# ---------------------------------------------------------------------------

class TestStage8ContractGeneration:
    def _dummy_profile(self, df: pl.DataFrame) -> dict:
        return {
            "dataset_name": "employees",
            "row_count": df.height,
            "column_count": df.width,
            "columns": {c: {"null_percentage": 0.0} for c in df.columns},
        }

    def test_returns_path(self, minimal_df, pipeline_config):
        profile = self._dummy_profile(minimal_df)
        path = _stage_8_generate_contract(minimal_df, "employees", profile, pipeline_config)
        assert isinstance(path, Path)
        assert path.exists()

    def test_contract_file_is_valid_json(self, minimal_df, pipeline_config):
        import json
        profile = self._dummy_profile(minimal_df)
        path = _stage_8_generate_contract(minimal_df, "employees", profile, pipeline_config)
        with open(path) as f:
            contract = json.load(f)
        assert "dataset_name" in contract
        assert contract["dataset_name"] == "employees"

    def test_contract_error_raises_ingestion_error(self, minimal_df, pipeline_config):
        with patch(
            "app.ingestion.services.ingestion_service.ContractGenerator.generate",
            side_effect=RuntimeError("template error"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                _stage_8_generate_contract(minimal_df, "d", {}, pipeline_config)
            assert exc_info.value.stage == "contract_generation"


# ---------------------------------------------------------------------------
# Stage 9: _SUCCESS marker
# ---------------------------------------------------------------------------

class TestStage9SuccessMarker:
    def test_creates_marker_file(self, tmp_path):
        fake_parquet = tmp_path / "lake" / "ds" / "partition_date=2026-05-15" / "batch_001.parquet"
        fake_parquet.parent.mkdir(parents=True)
        fake_parquet.touch()

        marker_path = _stage_9_write_success_marker(fake_parquet, "batch_001", 100, "1.0.0")
        assert marker_path.exists()
        assert marker_path.name == "_SUCCESS"

    def test_marker_is_in_partition_dir(self, tmp_path):
        partition_dir = tmp_path / "partition_date=2026-05-15"
        partition_dir.mkdir()
        parquet = partition_dir / "batch.parquet"
        parquet.touch()

        marker_path = _stage_9_write_success_marker(parquet, "batch_001", 50, "1.0.0")
        assert marker_path.parent == partition_dir

    def test_marker_error_raises_ingestion_error(self, tmp_path):
        with patch(
            "app.ingestion.services.ingestion_service.SuccessMarker.mark_success",
            side_effect=OSError("read-only filesystem"),
        ):
            fake_parquet = tmp_path / "p.parquet"
            fake_parquet.touch()
            with pytest.raises(IngestionServiceError) as exc_info:
                _stage_9_write_success_marker(fake_parquet, "b", 10, "1.0.0")
            assert exc_info.value.stage == "success_marker"


# ---------------------------------------------------------------------------
# Happy-path integration test (real temp CSV, real filesystem)
# ---------------------------------------------------------------------------

def _fake_write(tmp_path: Path, dataset: str = "employees") -> MagicMock:
    """
    Return a MagicMock for ParquetWriter.write that creates a real (empty)
    parquet file so downstream stages (profiler, marker) have a real path.
    """
    parquet_path = tmp_path / dataset / "partition_date=2026-05-15" / "batch_001.parquet"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.touch()

    mock = MagicMock(return_value=parquet_path)
    return mock


@pytest.fixture()
def _patched_write(pipeline_config):
    """Fixture that auto-patches ParquetWriter.write for the happy-path class."""
    parquet_path = pipeline_config.storage_dir / "employees" / "partition_date=2026-05-15" / "b.parquet"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.touch()
    with patch(
        "app.ingestion.services.ingestion_service.ParquetWriter.write",
        return_value=parquet_path,
    ):
        yield parquet_path


class TestRunIngestionPipelineHappyPath:
    """Happy-path tests.  ParquetWriter.write is patched to avoid the pyarrow
    dependency in the local (non-Docker) test environment."""

    @pytest.fixture(autouse=True)
    def _patch_parquet(self, pipeline_config):
        """Auto-patch write for every test in this class."""
        parquet_path = (
            pipeline_config.storage_dir
            / "employees"
            / "partition_date=2026-05-15"
            / "batch_001.parquet"
        )
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_path.touch()
        with patch(
            "app.ingestion.services.ingestion_service.ParquetWriter.write",
            return_value=parquet_path,
        ) as mock_write:
            self._parquet_path = parquet_path
            yield mock_write

    def test_returns_pipeline_result(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(
            filepath=sample_csv,
            dataset_name="employees",
            config=pipeline_config,
        )
        assert isinstance(result, PipelineResult)

    def test_status_is_success(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert result.status == "success"

    def test_ready_for_validation_is_true(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert result.ready_for_validation is True

    def test_row_count_matches_csv(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert result.row_count == 3  # 3 rows in sample_csv fixture

    def test_duplicate_count_detected(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        # Row 0 and Row 2 are identical data → 2 rows flagged as duplicates
        assert result.duplicate_count == 2

    def test_parquet_path_returned(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert "employees" in result.parquet_path

    def test_profile_file_exists(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert Path(result.profile_path).exists()

    def test_contract_file_exists(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert Path(result.contract_path).exists()

    def test_success_marker_exists(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        parquet_dir = Path(result.parquet_path).parent
        assert (parquet_dir / "_SUCCESS").exists()

    def test_batch_id_format(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert result.batch_id.startswith("batch_")
        assert len(result.batch_id) == len("batch_") + 12

    def test_execution_time_ms_is_positive(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        assert result.execution_time_ms > 0

    def test_stage_timings_have_all_keys(self, sample_csv, pipeline_config):
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        expected_stages = {
            "csv_load_and_normalise",
            "metadata_enrichment_and_hashing",
            "duplicate_detection",
            "parquet_write",
            "profiling",
            "contract_generation",
            "success_marker",
        }
        assert expected_stages == set(result.stage_timings.keys())

    def test_storage_dir_shortcut(self, sample_csv, tmp_path):
        shortcut = tmp_path / "shortcut_lake"
        parquet_path = shortcut / "employees" / "partition_date=2026-05-15" / "b.parquet"
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_path.touch()
        with patch(
            "app.ingestion.services.ingestion_service.ParquetWriter.write",
            return_value=parquet_path,
        ):
            result = run_ingestion_pipeline(
                sample_csv, "employees", storage_dir=str(shortcut)
            )
        assert "shortcut_lake" in result.parquet_path

    def test_to_dict_serialisable(self, sample_csv, pipeline_config):
        import json
        result = run_ingestion_pipeline(sample_csv, "employees", config=pipeline_config)
        json.dumps(result.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# Pipeline-level error propagation tests
# ---------------------------------------------------------------------------

class TestRunIngestionPipelineErrors:
    def test_missing_csv_raises_ingestion_error(self, tmp_path, pipeline_config):
        with pytest.raises(IngestionServiceError) as exc_info:
            run_ingestion_pipeline(tmp_path / "ghost.csv", "d", config=pipeline_config)
        assert exc_info.value.stage == "csv_load"

    def test_enrichment_failure_raises_ingestion_error(self, sample_csv, pipeline_config):
        with patch(
            "app.ingestion.services.ingestion_service.MetadataEnricher.enrich",
            side_effect=MetadataEnrichmentError("bad schema"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                run_ingestion_pipeline(sample_csv, "d", config=pipeline_config)
        assert exc_info.value.stage == "metadata_enrichment"

    def test_parquet_failure_raises_ingestion_error(self, sample_csv, pipeline_config):
        with patch(
            "app.ingestion.services.ingestion_service.ParquetWriter.write",
            side_effect=ParquetWriterError("disk full"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                run_ingestion_pipeline(sample_csv, "d", config=pipeline_config)
        assert exc_info.value.stage == "parquet_write"

    def test_profiling_failure_raises_ingestion_error(self, sample_csv, pipeline_config):
        with patch(
            "app.ingestion.services.ingestion_service.DatasetProfiler.profile",
            side_effect=RuntimeError("oom"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                run_ingestion_pipeline(sample_csv, "d", config=pipeline_config)
        assert exc_info.value.stage == "profiling"

    def test_contract_failure_raises_ingestion_error(self, sample_csv, pipeline_config):
        with patch(
            "app.ingestion.services.ingestion_service.ContractGenerator.generate",
            side_effect=RuntimeError("template error"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                run_ingestion_pipeline(sample_csv, "d", config=pipeline_config)
        assert exc_info.value.stage == "contract_generation"

    def test_success_marker_failure_raises_ingestion_error(self, sample_csv, pipeline_config):
        # Must also patch write so stage 6 succeeds before reaching stage 9
        parquet_path = (
            pipeline_config.storage_dir
            / "d" / "partition_date=2026-05-15" / "b.parquet"
        )
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        parquet_path.touch()
        with patch(
            "app.ingestion.services.ingestion_service.ParquetWriter.write",
            return_value=parquet_path,
        ), patch(
            "app.ingestion.services.ingestion_service.SuccessMarker.mark_success",
            side_effect=OSError("read-only fs"),
        ):
            with pytest.raises(IngestionServiceError) as exc_info:
                run_ingestion_pipeline(sample_csv, "d", config=pipeline_config)
        assert exc_info.value.stage == "success_marker"
