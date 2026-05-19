"""
app/platform/orchestration/task_scheduler.py
--------------------------------------------
Recurring task scheduler for Platform Intelligence pipeline runs.

This daemon is separate from Atharv's rule scheduler. Atharv's scheduler runs
individual saved validation rules; this scheduler triggers Manjunath's full
Prefect pipeline (profile → validate → suggest → detect → store) on cron.
"""

from __future__ import annotations

import asyncio
import random
import signal
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.daemon.cron import (
    classify_scheduler_status,
    cron_to_trigger,
    validate_cron_expression,
)
from app.db.session import close_db_engine, metadata_engine
from app.platform.data_access import validate_table_name
from app.platform.logger import get_logger
from app.platform.orchestration.execution_logger import log_pipeline_event
from app.platform.orchestration.flow_controller import (
    create_pipeline_run,
    run_full_pipeline,
)
from app.settings import get_settings

log = get_logger(__name__)


@dataclass(frozen=True)
class PipelineSchedule:
    schedule_id: int
    table_name: str
    schedule_cron: str
    is_enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


async def create_pipeline_schedule(
    table_name: str,
    schedule_cron: str,
    is_enabled: bool = True,
    description: str | None = None,
) -> PipelineSchedule:
    """Create a stored platform pipeline schedule."""
    validate_cron_expression(schedule_cron)
    validate_table_name(table_name)
    async with metadata_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO dq_platform.pipeline_schedules
                    (table_name, schedule_cron, is_enabled, description)
                VALUES
                    (:table_name, :schedule_cron, :is_enabled, :description)
                RETURNING schedule_id, table_name, schedule_cron, is_enabled,
                          description, created_at, updated_at
                """
            ),
            {
                "table_name": table_name,
                "schedule_cron": schedule_cron,
                "is_enabled": is_enabled,
                "description": description,
            },
        )
        return _schedule_from_row(result.mappings().one())


async def list_pipeline_schedules() -> list[PipelineSchedule]:
    """Return all platform pipeline schedules ordered by ID."""
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT schedule_id, table_name, schedule_cron, is_enabled,
                       description, created_at, updated_at
                FROM dq_platform.pipeline_schedules
                ORDER BY schedule_id
                """
            )
        )
        return [_schedule_from_row(row) for row in result.mappings().all()]


async def get_pipeline_schedule(schedule_id: int) -> PipelineSchedule | None:
    """Fetch one platform pipeline schedule."""
    async with metadata_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT schedule_id, table_name, schedule_cron, is_enabled,
                       description, created_at, updated_at
                FROM dq_platform.pipeline_schedules
                WHERE schedule_id = :schedule_id
                """
            ),
            {"schedule_id": schedule_id},
        )
        row = result.mappings().first()
    return _schedule_from_row(row) if row is not None else None


async def set_pipeline_schedule_enabled(
    schedule_id: int,
    is_enabled: bool,
) -> PipelineSchedule | None:
    """Enable or disable a stored platform pipeline schedule."""
    async with metadata_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE dq_platform.pipeline_schedules
                SET is_enabled = :is_enabled,
                    updated_at = NOW()
                WHERE schedule_id = :schedule_id
                RETURNING schedule_id, table_name, schedule_cron, is_enabled,
                          description, created_at, updated_at
                """
            ),
            {"schedule_id": schedule_id, "is_enabled": is_enabled},
        )
        row = result.mappings().first()
    return _schedule_from_row(row) if row is not None else None


async def run_scheduled_pipeline(
    schedule: PipelineSchedule,
    jitter_seconds: int | None = None,
) -> dict[str, Any]:
    """Execute one scheduled full-platform pipeline run."""
    settings = get_settings()
    jitter = (
        settings.pipeline_execution_jitter_seconds
        if jitter_seconds is None
        else jitter_seconds
    )
    if jitter > 0:
        delay = random.uniform(0, jitter)
        log.info(
            "Delaying platform schedule {sid} for {delay:.2f}s.",
            sid=schedule.schedule_id,
            delay=delay,
        )
        await asyncio.sleep(delay)

    run_id = await create_pipeline_run(
        schedule.table_name,
        metadata={"trigger": "schedule", "schedule_id": schedule.schedule_id},
    )
    await log_pipeline_event(
        run_id,
        "scheduler",
        f"Scheduled pipeline triggered by schedule {schedule.schedule_id}.",
        details={"schedule_cron": schedule.schedule_cron},
    )
    return await run_full_pipeline(table_name=schedule.table_name, run_id=run_id)


async def load_pipeline_schedules(scheduler: AsyncIOScheduler) -> int:
    """Load enabled cron schedules into an APScheduler instance."""
    schedules = await list_pipeline_schedules()
    scheduled_count = 0

    for schedule in schedules:
        scheduler_status = classify_scheduler_status(
            schedule.is_enabled,
            schedule.schedule_cron,
        )
        if scheduler_status != "schedulable":
            log.info(
                "Skipping platform schedule {sid} for {table}: {status}.",
                sid=schedule.schedule_id,
                table=schedule.table_name,
                status=scheduler_status,
            )
            continue

        scheduler.add_job(
            run_scheduled_pipeline,
            trigger=cron_to_trigger(schedule.schedule_cron),
            id=f"platform_pipeline_{schedule.schedule_id}",
            name=f"Platform pipeline: {schedule.table_name}",
            args=[schedule],
            coalesce=True,
            misfire_grace_time=60,
            max_instances=1,
            replace_existing=True,
        )
        scheduled_count += 1
        log.info(
            "Scheduled platform pipeline {sid} for '{table}' with cron '{cron}'.",
            sid=schedule.schedule_id,
            table=schedule.table_name,
            cron=schedule.schedule_cron,
        )

    return scheduled_count


async def run_platform_scheduler_forever() -> None:
    """Start the long-running platform pipeline scheduler daemon."""
    log.info("Starting Platform Intelligence scheduler")
    scheduler = AsyncIOScheduler(timezone="UTC")
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            try:
                loop.add_signal_handler(getattr(signal, signal_name), stop_event.set)
            except NotImplementedError:
                pass

    await load_pipeline_schedules(scheduler)
    scheduler.start()
    log.info("Platform scheduler started")

    try:
        await stop_event.wait()
    finally:
        log.info("Stopping Platform Intelligence scheduler")
        scheduler.shutdown(wait=False)
        await close_db_engine()


def main() -> None:
    asyncio.run(run_platform_scheduler_forever())


if __name__ == "__main__":
    main()


def _schedule_from_row(row) -> PipelineSchedule:
    return PipelineSchedule(
        schedule_id=row["schedule_id"],
        table_name=row["table_name"],
        schedule_cron=row["schedule_cron"],
        is_enabled=row["is_enabled"],
        description=row.get("description"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
