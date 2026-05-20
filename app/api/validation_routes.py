from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from app.platform.data_access import SourceDataAccessError
from app.platform.logger import get_logger
from app.platform.orchestration.flow_controller import (
    create_pipeline_run,
    run_full_pipeline,
)

log = get_logger(__name__)
router = APIRouter(prefix="/api/v1/validation", tags=["Validation Trigger"])


class ValidationTriggerRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1, max_length=200)
    batch_id: str = Field(..., min_length=1, max_length=200)
    parquet_path: str = Field(..., min_length=1)
    profile_path: str = Field(..., min_length=1)
    table_name: str | None = Field(default=None, min_length=1, max_length=200)


class ValidationTriggerResponse(BaseModel):
    status: Literal["ACKNOWLEDGED", "TRIGGERED"]
    dataset_name: str
    batch_id: str
    run_id: int | None = None
    table_name: str | None = None
    message: str


@router.post(
    "/trigger",
    response_model=ValidationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Acknowledge ingestion output and optionally trigger platform validation",
)
async def trigger_validation(
    request: ValidationTriggerRequest,
    background_tasks: BackgroundTasks,
) -> ValidationTriggerResponse:
    table_name = _resolve_table_name(request)
    if table_name is None:
        log.info(
            "Validation trigger acknowledged without table mapping: dataset={d}, batch={b}",
            d=request.dataset_name,
            b=request.batch_id,
        )
        return ValidationTriggerResponse(
            status="ACKNOWLEDGED",
            dataset_name=request.dataset_name,
            batch_id=request.batch_id,
            message=(
                "Validation trigger acknowledged; no PostgreSQL table mapping was "
                "provided, so no Platform Intelligence pipeline run was started."
            ),
        )

    try:
        run_id = await create_pipeline_run(
            table_name,
            metadata={
                "trigger": "ingestion",
                "dataset_name": request.dataset_name,
                "batch_id": request.batch_id,
                "parquet_path": request.parquet_path,
                "profile_path": request.profile_path,
            },
        )
    except SourceDataAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    background_tasks.add_task(_run_platform_pipeline_background, table_name, run_id)
    return ValidationTriggerResponse(
        status="TRIGGERED",
        dataset_name=request.dataset_name,
        batch_id=request.batch_id,
        run_id=run_id,
        table_name=table_name,
        message=(
            "Validation trigger accepted; Platform Intelligence pipeline run "
            f"{run_id} was started."
        ),
    )


def _resolve_table_name(request: ValidationTriggerRequest) -> str | None:
    if request.table_name:
        return request.table_name
    if "." in request.dataset_name:
        return request.dataset_name
    return None


async def _run_platform_pipeline_background(table_name: str, run_id: int) -> None:
    try:
        await run_full_pipeline(table_name=table_name, run_id=run_id)
    except Exception as exc:
        log.error(
            "Platform validation pipeline failed after trigger: run_id={r}, table={t}, error={e}",
            r=run_id,
            t=table_name,
            e=exc,
        )
