"""
app/ingestion/services/ingestion_service.py
===========================================
Production-grade CSV ingestion orchestration service.

Orchestrates the full 9-stage data ingestion pipeline in a single, isolated,
self-contained module.  Zero modifications to any existing daemon, scheduler,
executor, or registry modules.

Pipeline stages
---------------
1.  CSV ingestion            – CSVConnector
2.  Column normalisation     – performed by CSVConnector.load()
3.  Metadata enrichment      – MetadataEnricher
4.  Row hash generation      – MetadataEnricher (SHA-256, data columns only)
5.  Duplicate detection      – DuplicateDetector
6.  Partitioned Parquet write – ParquetWriter
7.  Dataset profiling        – DatasetProfiler
8.  Contract generation      – ContractGenerator
9.  _SUCCESS marker          – SuccessMarker

Public surface
--------------
    run_ingestion_pipeline(filepath, dataset_name, *, config, storage_dir) -> PipelineResult

All other helpers are module-private (_prefixed).

Usage example
-------------
    from app.ingestion.services.ingestion_service import run_ingestion_pipeline

    result = run_ingestion_pipeline(
        filepath="/data/raw/employees_2026.csv",
        dataset_name="employees",
    )
    # result.parquet_path, result.profile_path, result.contract_path ...
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

# ---------------------------------------------------------------------------
# Ingestion sub-modules – READ ONLY, never modified
# ---------------------------------------------------------------------------
from app.ingestion.connectors.csv_connector import CSVConnector, CSVConnectorConfig
from app.ingestion.utils.metadata import MetadataEnricher, MetadataEnrichmentError
from app.ingestion.processors.duplicate_detector import (
    DuplicateDetector,
    DuplicateDetectionError,
)
from app.ingestion.writers.parquet_writer import ParquetWriter, ParquetWriterError
from app.ingestion.writers.success_marker import SuccessMarker
from app.ingestion.profiling.profiler import DatasetProfiler
from app.ingestion.contracts.contract_generator import ContractGenerator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/tmp/data_lake"))
_DEFAULT_PROFILING_DIR = Path(os.getenv("PROFILING_DIR", "/tmp/data_lake/profiling"))
_DEFAULT_CONTRACTS_DIR = Path(os.getenv("CONTRACTS_DIR", "/tmp/data_lake/contracts"))
_SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Public result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PipelineResult:
    """
    Immutable result contract returned by :func:`run_ingestion_pipeline`.

    All paths are absolute strings, safe to pass as JSON values.
    """

    status: str
    """``'success'`` on a fully completed pipeline run."""

    batch_id: str
    """Unique identifier for this ingestion batch (``batch_<12-hex>`` format)."""

    dataset_name: str
    """Logical name of the ingested dataset."""

    row_count: int
    """Total rows written to the Parquet partition."""

    parquet_path: str
    """Absolute path of the partitioned ``.parquet`` file."""

    profile_path: str
    """Absolute path of the JSON profile file."""

    contract_path: str
    """Absolute path of the JSON data-contract file."""

    ready_for_validation: bool
    """``True`` when all 9 stages completed without error."""

    # ---- supplemental diagnostics ----
    duplicate_count: int = 0
    """Number of rows flagged as duplicates (``__is_duplicate == True``)."""

    execution_time_ms: int = 0
    """Wall-clock time for the full pipeline in milliseconds."""

    stage_timings: dict[str, int] = field(default_factory=dict)
    """Per-stage wall-clock breakdown in milliseconds."""

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (JSON-safe)."""
        return {
            "status": self.status,
            "batch_id": self.batch_id,
            "dataset_name": self.dataset_name,
            "row_count": self.row_count,
            "parquet_path": self.parquet_path,
            "profile_path": self.profile_path,
            "contract_path": self.contract_path,
            "ready_for_validation": self.ready_for_validation,
            "duplicate_count": self.duplicate_count,
            "execution_time_ms": self.execution_time_ms,
            "stage_timings": self.stage_timings,
        }


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class IngestionServiceError(Exception):
    """Base exception for all ingestion service failures."""

    def __init__(self, stage: str, message: str, cause: BaseException | None = None) -> None:
        self.stage = stage
        super().__init__(f"[stage={stage}] {message}")
        self.__cause__ = cause


# ---------------------------------------------------------------------------
# Internal pipeline config
# ---------------------------------------------------------------------------

@dataclass
class IngestionPipelineConfig:
    """
    Optional configuration to customise pipeline behaviour.

    All parameters have production-safe defaults; the caller only needs to
    override values that differ from the defaults.

    Parameters
    ----------
    csv_config:
        :class:`CSVConnectorConfig` forwarded directly to the CSV connector.
    storage_dir:
        Root directory for Parquet partitions.
        Reads ``$STORAGE_DIR`` env-var; falls back to ``/tmp/data_lake``.
    profiling_dir:
        Root directory for JSON profiles.
        Reads ``$PROFILING_DIR``; falls back to ``/tmp/data_lake/profiling``.
    contracts_dir:
        Root directory for JSON contracts.
        Reads ``$CONTRACTS_DIR``; falls back to ``/tmp/data_lake/contracts``.
    schema_version:
        Semantic version string embedded in the Parquet writer, success
        marker, and data contract.
    duplicate_subset:
        Optional list of column names to use for duplicate-detection hashing.
        ``None`` → hash all columns (excluding metadata columns).
    """

    csv_config: CSVConnectorConfig = field(default_factory=CSVConnectorConfig)
    storage_dir: Path = field(default_factory=lambda: _DEFAULT_STORAGE_DIR)
    profiling_dir: Path = field(default_factory=lambda: _DEFAULT_PROFILING_DIR)
    contracts_dir: Path = field(default_factory=lambda: _DEFAULT_CONTRACTS_DIR)
    schema_version: str = _SCHEMA_VERSION
    duplicate_subset: list[str] | None = None


# ---------------------------------------------------------------------------
# Private stage helpers
# ---------------------------------------------------------------------------

def _ms(start: float) -> int:
    """Return elapsed milliseconds since *start* (from ``time.perf_counter()``)."""
    return int((time.perf_counter() - start) * 1000)


def _stage_1_load_csv(
    filepath: str | Path,
    config: IngestionPipelineConfig,
) -> pl.DataFrame:
    """
    Stage 1 + 2: Load CSV and normalise column names to snake_case.

    Column normalisation is handled transparently by :class:`CSVConnector`.
    """
    t0 = time.perf_counter()
    logger.info("[Stage 1/9] CSV ingestion | file='{}'", filepath)
    try:
        connector = CSVConnector(config.csv_config)
        df = connector.load(filepath)
    except Exception as exc:
        raise IngestionServiceError("csv_load", str(exc), exc) from exc
    logger.info("[Stage 1+2] CSV loaded and columns normalised | rows={} cols={} elapsed={}ms",
                df.height, df.width, _ms(t0))
    return df


def _stage_3_4_enrich_metadata(
    df: pl.DataFrame,
    batch_id: str,
    dataset_name: str,
) -> pl.DataFrame:
    """
    Stage 3 + 4: Metadata enrichment and SHA-256 row-hash generation.

    :class:`MetadataEnricher` adds ``__batch_id``, ``__ingested_at``,
    ``__partition_date``, ``__source_name``, ``__source_type``,
    ``__record_id``, ``__row_hash``, and ``__is_duplicate`` in one pass.
    """
    t0 = time.perf_counter()
    logger.info("[Stage 3+4] Metadata enrichment & row-hash generation | batch_id='{}'", batch_id)
    try:
        enricher = MetadataEnricher(
            batch_id=batch_id,
            source_name=dataset_name,
            source_type="csv",
        )
        df = enricher.enrich(df)
    except MetadataEnrichmentError as exc:
        raise IngestionServiceError("metadata_enrichment", str(exc), exc) from exc
    logger.info("[Stage 3+4] Enrichment complete | rows={} elapsed={}ms", df.height, _ms(t0))
    return df


def _stage_5_detect_duplicates(
    df: pl.DataFrame,
    subset: list[str] | None,
) -> tuple[pl.DataFrame, int]:
    """
    Stage 5: Duplicate detection via vectorised row-hashing.

    Returns the augmented DataFrame and the total duplicate row count.
    Note: MetadataEnricher already sets ``__is_duplicate`` via cum_count
    within the batch.  This stage re-runs DuplicateDetector on the data
    columns (excluding metadata ``__`` prefixed columns) for an independent,
    cross-batch hash comparison and generates duplicate stats.
    """
    t0 = time.perf_counter()
    logger.info("[Stage 5] Duplicate detection")
    try:
        # Resolve the subset to data-only columns if not explicitly provided
        effective_subset = subset or [
            c for c in df.columns if not c.startswith("__")
        ]
        detector = DuplicateDetector(subset=effective_subset)
        df, stats = detector.process(df)
        dup_count = int(stats.get("total_duplicates", 0))
    except DuplicateDetectionError as exc:
        raise IngestionServiceError("duplicate_detection", str(exc), exc) from exc
    logger.info(
        "[Stage 5] Duplicate detection complete | duplicates={} ({:.1f}%) elapsed={}ms",
        dup_count,
        float(stats.get("duplicate_percentage", 0.0)),
        _ms(t0),
    )
    return df, dup_count


def _stage_6_write_parquet(
    df: pl.DataFrame,
    dataset_name: str,
    batch_id: str,
    partition_date: str,
    config: IngestionPipelineConfig,
) -> Path:
    """
    Stage 6: Write enriched DataFrame to a partitioned Snappy Parquet file.

    Writes atomically via a ``.tmp`` suffix, then renames.
    """
    t0 = time.perf_counter()
    logger.info("[Stage 6] Partitioned Parquet write | dataset='{}' partition='{}'",
                dataset_name, partition_date)
    try:
        writer = ParquetWriter(
            base_output_dir=config.storage_dir,
            schema_version=config.schema_version,
        )
        parquet_path = writer.write(
            df=df,
            dataset_name=dataset_name,
            batch_id=batch_id,
            partition_date=partition_date,
        )
    except ParquetWriterError as exc:
        raise IngestionServiceError("parquet_write", str(exc), exc) from exc
    logger.info("[Stage 6] Parquet written | path='{}' elapsed={}ms", parquet_path, _ms(t0))
    return parquet_path


def _stage_7_profile_dataset(
    df: pl.DataFrame,
    dataset_name: str,
    batch_id: str,
    config: IngestionPipelineConfig,
) -> tuple[Path, dict[str, Any]]:
    """
    Stage 7: Compute structural statistics and persist a JSON profile.

    Returns both the profile path and the raw profile dict (needed by stage 8).
    """
    t0 = time.perf_counter()
    logger.info("[Stage 7] Dataset profiling | dataset='{}'", dataset_name)
    profile_output_dir = str(config.profiling_dir)
    try:
        profiler = DatasetProfiler(
            dataset_name=f"{dataset_name}_{batch_id}",
            output_base_dir=profile_output_dir,
        )
        profile_data = profiler.profile(df)
        profile_path = profiler.save_profile(profile_data)
    except Exception as exc:
        raise IngestionServiceError("profiling", str(exc), exc) from exc
    logger.info("[Stage 7] Profile saved | path='{}' elapsed={}ms", profile_path, _ms(t0))
    return profile_path, profile_data


def _stage_8_generate_contract(
    df: pl.DataFrame,
    dataset_name: str,
    profile_data: dict[str, Any],
    config: IngestionPipelineConfig,
) -> Path:
    """
    Stage 8: Derive and persist a JSON data contract from schema + profile.
    """
    t0 = time.perf_counter()
    logger.info("[Stage 8] Contract generation | dataset='{}'", dataset_name)
    try:
        generator = ContractGenerator(output_base_dir=str(config.contracts_dir))
        contract = generator.generate(
            dataset_name=dataset_name,
            schema=dict(df.schema),
            profiling_metadata=profile_data,
            version=config.schema_version,
        )
        contract_path = generator.save_contract(
            dataset_name=dataset_name,
            contract=contract,
            version=config.schema_version,
        )
    except Exception as exc:
        raise IngestionServiceError("contract_generation", str(exc), exc) from exc
    logger.info("[Stage 8] Contract saved | path='{}' elapsed={}ms", contract_path, _ms(t0))
    return contract_path


def _stage_9_write_success_marker(
    parquet_path: Path,
    batch_id: str,
    row_count: int,
    schema_version: str,
) -> Path:
    """
    Stage 9: Write an atomic ``_SUCCESS`` JSON marker in the Parquet partition dir.
    """
    t0 = time.perf_counter()
    partition_dir = parquet_path.parent
    logger.info("[Stage 9] Writing _SUCCESS marker | dir='{}'", partition_dir)
    try:
        marker = SuccessMarker(output_dir=partition_dir)
        marker_path = marker.mark_success(
            batch_id=batch_id,
            row_count=row_count,
            schema_version=schema_version,
        )
    except Exception as exc:
        raise IngestionServiceError("success_marker", str(exc), exc) from exc
    logger.info("[Stage 9] _SUCCESS marker written | path='{}' elapsed={}ms", marker_path, _ms(t0))
    return marker_path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_ingestion_pipeline(
    filepath: str | Path,
    dataset_name: str,
    *,
    config: IngestionPipelineConfig | None = None,
    storage_dir: str | Path | None = None,
) -> PipelineResult:
    """
    Execute the full 9-stage CSV ingestion pipeline.

    This is the **sole public entry point** of this module.  All callers
    should import and invoke only this function.

    Parameters
    ----------
    filepath:
        Absolute or relative path to the source CSV file.
    dataset_name:
        Logical name of the dataset.  Used as the top-level directory name
        for Parquet partitions, profiles, and contracts.
    config:
        Optional :class:`IngestionPipelineConfig` to customise connector
        settings, storage paths, schema version, or duplicate-detection
        column subset.  Defaults to sensible production values when omitted.
    storage_dir:
        Convenience shortcut to override the Parquet base directory without
        constructing a full :class:`IngestionPipelineConfig`.  Ignored when
        *config* is provided.

    Returns
    -------
    PipelineResult
        Frozen dataclass with paths, counts, timings, and a
        ``ready_for_validation`` flag.

    Raises
    ------
    IngestionServiceError
        Raised with ``stage`` attribute set to the failing stage name on any
        unrecoverable pipeline error.  Caller can inspect ``.stage`` to route
        to the appropriate error-handling branch.

    Examples
    --------
    Basic usage::

        from app.ingestion.services.ingestion_service import run_ingestion_pipeline

        result = run_ingestion_pipeline(
            filepath="/data/raw/sales_2026.csv",
            dataset_name="sales",
        )
        print(result.to_dict())

    Custom storage path::

        result = run_ingestion_pipeline(
            filepath="/tmp/upload/hr.csv",
            dataset_name="hr_employees",
            storage_dir="/mnt/datalake",
        )

    Custom connector (semicolon-delimited, Latin-1)::

        from app.ingestion.connectors.csv_connector import CSVConnectorConfig
        from app.ingestion.services.ingestion_service import (
            IngestionPipelineConfig,
            run_ingestion_pipeline,
        )

        cfg = IngestionPipelineConfig(
            csv_config=CSVConnectorConfig(delimiter=";", encoding="latin-1"),
            storage_dir="/mnt/datalake",
        )
        result = run_ingestion_pipeline("data/eu_sales.csv", "eu_sales", config=cfg)
    """
    pipeline_start = time.perf_counter()

    # ---- resolve config ---------------------------------------------------
    if config is None:
        config = IngestionPipelineConfig()
        if storage_dir is not None:
            config = IngestionPipelineConfig(storage_dir=Path(storage_dir))

    # ---- generate batch identity ------------------------------------------
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stage_timings: dict[str, int] = {}

    logger.info(
        "=== Ingestion pipeline START | dataset='{}' batch_id='{}' file='{}' ===",
        dataset_name,
        batch_id,
        filepath,
    )

    # ---- Stage 1 + 2: CSV load + column normalisation ---------------------
    t = time.perf_counter()
    df = _stage_1_load_csv(filepath, config)
    stage_timings["csv_load_and_normalise"] = _ms(t)

    # ---- Stage 3 + 4: Metadata enrichment + row hash ----------------------
    t = time.perf_counter()
    df = _stage_3_4_enrich_metadata(df, batch_id, dataset_name)
    stage_timings["metadata_enrichment_and_hashing"] = _ms(t)

    # ---- Stage 5: Duplicate detection -------------------------------------
    t = time.perf_counter()
    df, duplicate_count = _stage_5_detect_duplicates(df, config.duplicate_subset)
    stage_timings["duplicate_detection"] = _ms(t)

    # ---- Stage 6: Partitioned Parquet write --------------------------------
    t = time.perf_counter()
    parquet_path = _stage_6_write_parquet(df, dataset_name, batch_id, partition_date, config)
    stage_timings["parquet_write"] = _ms(t)

    row_count = df.height

    # ---- Stage 7: Dataset profiling ----------------------------------------
    t = time.perf_counter()
    profile_path, profile_data = _stage_7_profile_dataset(df, dataset_name, batch_id, config)
    stage_timings["profiling"] = _ms(t)

    # ---- Stage 8: Contract generation --------------------------------------
    t = time.perf_counter()
    contract_path = _stage_8_generate_contract(df, dataset_name, profile_data, config)
    stage_timings["contract_generation"] = _ms(t)

    # ---- Stage 9: _SUCCESS marker ------------------------------------------
    t = time.perf_counter()
    _stage_9_write_success_marker(parquet_path, batch_id, row_count, config.schema_version)
    stage_timings["success_marker"] = _ms(t)

    total_ms = _ms(pipeline_start)

    logger.info(
        "=== Ingestion pipeline COMPLETE | dataset='{}' batch_id='{}' rows={} "
        "duplicates={} total_ms={} ===",
        dataset_name,
        batch_id,
        row_count,
        duplicate_count,
        total_ms,
    )

    return PipelineResult(
        status="success",
        batch_id=batch_id,
        dataset_name=dataset_name,
        row_count=row_count,
        parquet_path=str(parquet_path),
        profile_path=str(profile_path),
        contract_path=str(contract_path),
        ready_for_validation=True,
        duplicate_count=duplicate_count,
        execution_time_ms=total_ms,
        stage_timings=stage_timings,
    )
