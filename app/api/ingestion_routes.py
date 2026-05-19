"""
app/api/ingestion_routes.py
===========================
Enterprise FastAPI router for CSV data ingestion.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from loguru import logger
from pydantic import BaseModel, Field

# We import the processing services built in previous steps.
# In a real architecture, these might be injected via DI.
from app.ingestion.utils.metadata import MetadataEnricher, MetadataEnrichmentError
from app.ingestion.processors.duplicate_detector import DuplicateDetector, DuplicateDetectionError
from app.ingestion.writers.parquet_writer import ParquetWriter, ParquetWriterError
from app.services.validation_trigger import ValidationTriggerService, ValidationTriggerError

import json
from fastapi.concurrency import run_in_threadpool
from app.ingestion.services.ingestion_service import run_ingestion_pipeline, IngestionServiceError


router = APIRouter(prefix="/ingestion", tags=["Data Ingestion"])

# Configurable storage path -- in prod, this comes from settings
BASE_STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/tmp/data_lake"))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class IngestionResponse(BaseModel):
    """Data contract for successful ingestion."""
    batch_id: str = Field(..., description="Unique identifier for the ingestion batch.")
    dataset_name: str = Field(..., description="The name of the dataset.")
    row_count: int = Field(..., description="Number of rows processed.")
    output_path: str = Field(..., description="Path to the created Parquet file.")

class PipelineResponse(BaseModel):
    """Response model for the 9-stage orchestration pipeline."""
    status: str
    batch_id: str
    dataset_name: str
    row_count: int
    parquet_path: str
    profile_path: str
    contract_path: str
    ready_for_validation: bool
    duplicate_count: int
    execution_time_ms: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def remove_temp_file(path: str) -> None:
    """Background task to remove temporary files securely."""
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.debug("Cleaned up temp file: {}", path)
    except Exception as e:
        logger.error("Failed to clean up temp file {}: {}", path, e)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/csv", 
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a CSV File"
)
async def ingest_csv(
    background_tasks: BackgroundTasks,
    dataset_name: str,
    file: UploadFile = File(...)
) -> IngestionResponse:
    """
    Ingest a CSV payload into the Data Platform.
    
    Validates the CSV, streams it to a local temporary file, processes it via Polars 
    (Enrichment -> Duplicate Detection -> Parquet Partitioning), and cleans up in the background.
    """
    logger.info("Received ingestion request for dataset='{}', filename='{}'", dataset_name, file.filename)

    # 1. Validate File Type
    if not file.filename.endswith(".csv") and file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
        logger.error("Invalid file type uploaded. Expected CSV, got {}", file.content_type)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid file format. Only CSV files are allowed."
        )

    # 2. Stage to Temp File securely
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    partition_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    fd, temp_file_path = tempfile.mkstemp(suffix=".csv", prefix=f"{batch_id}_")
    try:
        # Stream file to disk to avoid memory bloat before Polars reads it natively
        with open(fd, "wb") as f_out:
            while chunk := await file.read(8192 * 1024):
                f_out.write(chunk)
                
        # Register cleanup background task
        background_tasks.add_task(remove_temp_file, temp_file_path)

        # 3. Read -> Enrich -> Deduplicate -> Write
        try:
            logger.debug("Loading temporary CSV into Polars: {}", temp_file_path)
            df = pl.read_csv(temp_file_path, infer_schema_length=10000)
            
            # Enrichment
            enricher = MetadataEnricher(batch_id=batch_id, source_name=dataset_name, source_type="csv")
            df = enricher.enrich(df)
            
            # Duplicate Detection
            detector = DuplicateDetector()
            df, _ = detector.process(df)
            
            # Parquet Write
            writer = ParquetWriter(base_output_dir=BASE_STORAGE_DIR)
            output_path = writer.write(
                df=df,
                dataset_name=dataset_name,
                batch_id=batch_id,
                partition_date=partition_date
            )
            
        except (MetadataEnrichmentError, DuplicateDetectionError, ParquetWriterError) as be:
            logger.exception("Business logic error during processing.")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(be)
            )
        except Exception as e:
            logger.exception("Unexpected system error during ingestion.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}"
            )

        # 4. Asynchronously notify the validation engine (non-blocking, non-fatal)
        async def _fire_validation_trigger() -> None:
            try:
                trigger_svc = ValidationTriggerService()
                await trigger_svc.trigger_validation(
                    dataset_name=dataset_name,
                    batch_id=batch_id,
                    parquet_path=str(output_path),
                    profile_path="",  # profiling not run in HTTP path; placeholder
                )
            except ValidationTriggerError as vte:
                logger.warning("Validation trigger failed for batch '{}': {}", batch_id, vte)

        background_tasks.add_task(_fire_validation_trigger)

        # 4. Construct Response Contracts
        return IngestionResponse(
            batch_id=batch_id,
            dataset_name=dataset_name,
            row_count=df.height,
            output_path=str(output_path)
        )

    except HTTPException:
        # Bubbling expected Fast API errors up directly
        raise
    except Exception as general_err:
        logger.error("Failed to spool file upload: {}", general_err)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process file upload.")


@router.post(
    "/datasets/upload/csv",
    response_model=PipelineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a CSV File using Orchestration Service"
)
async def upload_dataset_csv(
    background_tasks: BackgroundTasks,
    dataset_name: str,
    file: UploadFile = File(...)
) -> PipelineResponse:
    """
    Ingest a CSV payload into the Data Platform using the isolated 9-stage orchestration pipeline.
    """
    logger.info("Received pipeline ingestion request for dataset='{}', filename='{}'", dataset_name, file.filename)

    if not file.filename.endswith(".csv") and file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
        logger.error("Invalid file type uploaded. Expected CSV, got {}", file.content_type)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Invalid file format. Only CSV files are allowed."
        )

    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    fd, temp_file_path = tempfile.mkstemp(suffix=".csv", prefix=f"{batch_id}_")
    
    try:
        with open(fd, "wb") as f_out:
            while chunk := await file.read(8192 * 1024):
                f_out.write(chunk)
                
        background_tasks.add_task(remove_temp_file, temp_file_path)

        try:
            result = await run_in_threadpool(
                run_ingestion_pipeline,
                filepath=temp_file_path,
                dataset_name=dataset_name
            )
        except IngestionServiceError as be:
            logger.exception("Pipeline error at stage {}: {}", be.stage, be)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(be)
            )

        async def _fire_validation_trigger() -> None:
            try:
                trigger_svc = ValidationTriggerService()
                await trigger_svc.trigger_validation(
                    dataset_name=dataset_name,
                    batch_id=result.batch_id,
                    parquet_path=result.parquet_path,
                    profile_path=result.profile_path,
                )
            except ValidationTriggerError as vte:
                logger.warning("Validation trigger failed for batch '{}': {}", result.batch_id, vte)

        background_tasks.add_task(_fire_validation_trigger)

        return PipelineResponse(**result.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected system error during pipeline ingestion.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.get(
    "/datasets/profile/{dataset_name}",
    summary="Get Dataset Profile",
)
async def get_dataset_profile(dataset_name: str):
    """
    Retrieve the most recent dataset profile JSON.
    """
    profiling_dir = Path(os.getenv("PROFILING_DIR", "/tmp/data_lake/profiling"))
    
    matches = list(profiling_dir.glob(f"{dataset_name}_*/latest/profile.json"))
    if not matches:
        raise HTTPException(status_code=404, detail="Profile not found for dataset.")
        
    latest_profile_path = max(matches, key=os.path.getmtime)
    
    try:
        with open(latest_profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read profile file: {}", e)
        raise HTTPException(status_code=500, detail="Error reading profile.")


@router.get(
    "/datasets/contracts/{dataset_name}",
    summary="Get Dataset Contract",
)
async def get_dataset_contract(dataset_name: str, version: str = "1.0.0"):
    """
    Retrieve the generated dataset contract JSON.
    """
    contracts_dir = Path(os.getenv("CONTRACTS_DIR", "/tmp/data_lake/contracts"))
    contract_path = contracts_dir / dataset_name / f"contract_v{version}.json"
    
    if not contract_path.exists():
        raise HTTPException(status_code=404, detail="Contract not found for dataset.")
        
    try:
        with open(contract_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to read contract file: {}", e)
        raise HTTPException(status_code=500, detail="Error reading contract.")
