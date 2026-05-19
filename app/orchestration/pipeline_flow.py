"""
app/orchestration/pipeline_flow.py
==================================
Enterprise Prefect orchestration flow for the Data Quality Platform pipeline.

Orchestrates the lifecycle of CSV processing from read to contract generation.
Supports automated retries, dependency structuring, and failure recovery.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from loguru import logger
from prefect import flow, task
from prefect.tasks import task_input_hash

from app.ingestion.utils.metadata import MetadataEnricher
from app.ingestion.processors.duplicate_detector import DuplicateDetector
from app.ingestion.writers.parquet_writer import ParquetWriter
from app.ingestion.profiling.profiler import DatasetProfiler
from app.ingestion.contracts.contract_generator import ContractGenerator
from app.services.validation_trigger import ValidationTriggerService, ValidationTriggerError


BASE_STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/tmp/data_lake"))


# ---------------------------------------------------------------------------
# Prefect Tasks
# ---------------------------------------------------------------------------

@task(retries=2, retry_delay_seconds=10, log_prints=True)
def read_csv_artifact(filepath: str) -> pl.DataFrame:
    """Reads the CSV file natively into Polars."""
    logger.info("Reading CSV asset from {} into Polars DataFrame.", filepath)
    return pl.read_csv(filepath, infer_schema_length=5000)

@task(retries=2, retry_delay_seconds=5, log_prints=True)
def generate_metadata(df: pl.DataFrame, dataset_name: str, batch_id: str) -> pl.DataFrame:
    """Enriches the dataset with universally required metadata and standardises columns."""
    enricher = MetadataEnricher(batch_id=batch_id, source_name=dataset_name, source_type="csv")
    return enricher.enrich(df)

@task(retries=2, retry_delay_seconds=5, log_prints=True)
def detect_duplicates(df: pl.DataFrame) -> pl.DataFrame:
    """Appends duplication states contextually via row hashes."""
    detector = DuplicateDetector()
    deduped_df, _ = detector.process(df)
    return deduped_df

@task(retries=3, retry_delay_seconds=15, log_prints=True)
def write_to_parquet(df: pl.DataFrame, dataset_name: str, batch_id: str) -> str:
    """Writes the curated dataset to partitioned Parquet clusters and issues markers."""
    writer = ParquetWriter(base_output_dir=BASE_STORAGE_DIR)
    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = writer.write(df, dataset_name=dataset_name, batch_id=batch_id, partition_date=partition_date)
    return str(out_path)

@task(retries=2, retry_delay_seconds=10, log_prints=True)
def run_dataset_profiling(df: pl.DataFrame, dataset_name: str, batch_id: str) -> str:
    """Generates structural profiling and descriptive statistics of the batch ingest."""
    profiler = DatasetProfiler()
    target_json_path = BASE_STORAGE_DIR / dataset_name / "profiles" / f"profile_{batch_id}.json"
    profiler.profile(df, target_json_path)
    return str(target_json_path)

@task(retries=2, retry_delay_seconds=5, log_prints=True)
def generate_dataset_contract(df: pl.DataFrame, dataset_name: str, batch_id: str, profile_path: str) -> str:
    """Combines physical schemas and statistical profiles generating the active dataset contract."""
    generator = ContractGenerator()
    
    # Load acquired profile via basic JSON loading
    import json
    with open(profile_path, "r", encoding="utf-8") as f:
        profiling_metadata = json.load(f)
        
    contract = generator.generate_contract(
        dataset_name=dataset_name,
        df_schema=df.schema,
        profiling_metadata=profiling_metadata,
        base_storage_path=str(BASE_STORAGE_DIR)
    )
    
    contract_path = BASE_STORAGE_DIR / dataset_name / "contracts" / f"contract_{batch_id}.json"
    generator.save_contract(contract, contract_path)
    return str(contract_path)


# ---------------------------------------------------------------------------
# Validation Trigger Task
# ---------------------------------------------------------------------------

@task(retries=3, retry_delay_seconds=10, log_prints=True)
async def trigger_validation_task(
    dataset_name: str, batch_id: str, parquet_path: str, profile_path: str
) -> dict:
    """Asynchronously notifies the validation engine that a new batch is ready."""
    service = ValidationTriggerService()
    try:
        result = await service.trigger_validation(
            dataset_name=dataset_name,
            batch_id=batch_id,
            parquet_path=parquet_path,
            profile_path=profile_path,
        )
        logger.info("Validation engine acknowledged batch '{}': {}", batch_id, result)
        return result
    except ValidationTriggerError as e:
        # Non-fatal: log and continue — data is already safely written
        logger.warning("Validation trigger failed for batch '{}': {}", batch_id, e)
        return {"status": "trigger_failed", "reason": str(e)}


# ---------------------------------------------------------------------------
# Orchestration Flow
# ---------------------------------------------------------------------------

@flow(name="Enterprise CSV Ingestion Pipeline", log_prints=True)
def run_ingestion_pipeline(filepath: str, dataset_name: str) -> dict[str, str]:
    """
    Main orchestration block defining pipeline dependencies and sequencing.
    Resolves data quality processing end to end resiliently via Prefect.
    """
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    logger.info("Initializing Prefect run for {}; batch_id={}", dataset_name, batch_id)
    
    try:
        # Phase 1. IO Source Access
        df = read_csv_artifact(filepath)
        
        # Phase 2. Metadata Governance
        df = generate_metadata(df, dataset_name, batch_id)
        
        # Phase 3. De-duplication Logic
        df = detect_duplicates(df)
        
        # Phase 4. Curated Parquet Storage
        parquet_path = write_to_parquet(df, dataset_name, batch_id)
        
        # Phase 5. Quality Profiling 
        profile_path = run_dataset_profiling(df, dataset_name, batch_id)
        
        # Phase 6. Schema Governance Contracting
        contract_path = generate_dataset_contract(df, dataset_name, batch_id, profile_path)

        # Phase 7. Trigger Downstream Validation Engine
        validation_result = trigger_validation_task(
            dataset_name=dataset_name,
            batch_id=batch_id,
            parquet_path=parquet_path,
            profile_path=profile_path,
        )

        logger.info("Ingestion Pipeline fully materialized successfully.")

        return {
            "status": "success",
            "batch_id": batch_id,
            "parquet_output": parquet_path,
            "profile_output": profile_path,
            "contract_output": contract_path,
            "validation_trigger": validation_result,
        }
    except Exception as e:
        logger.error("Pipeline failure on batch_id {}: {}", batch_id, e)
        raise
