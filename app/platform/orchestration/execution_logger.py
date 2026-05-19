"""
app/platform/orchestration/execution_logger.py
----------------------------------------------
Persistent execution logging for Platform Intelligence pipeline runs.

Loguru gives runtime logs; this module stores audit events in PostgreSQL so the
UI/API can show exactly which orchestration stage ran, failed, or was skipped.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.db.session import metadata_engine
from app.platform.logger import get_logger

log = get_logger(__name__)


async def log_pipeline_event(
    run_id: int | None,
    stage: str,
    message: str,
    level: str = "INFO",
    details: dict[str, Any] | None = None,
) -> None:
    """Persist an orchestration event without letting logging failures break a run."""
    if run_id is None:
        return

    try:
        async with metadata_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO dq_platform.pipeline_events
                        (run_id, stage, level, message, details, created_at)
                    VALUES
                        (:run_id, :stage, :level, :message, CAST(:details AS jsonb), :created_at)
                    """
                ),
                {
                    "run_id": run_id,
                    "stage": stage,
                    "level": level.upper(),
                    "message": message,
                    "details": json.dumps(details or {}, default=str),
                    "created_at": datetime.now(UTC),
                },
            )
    except Exception as exc:
        log.warning(
            "Failed to persist pipeline event for run_id={r}, stage={s}: {e}",
            r=run_id,
            s=stage,
            e=exc,
        )
