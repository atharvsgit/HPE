"""
app/platform/profiling/profiler.py
------------------------------------
Main data profiling engine.

Queries a PostgreSQL table via SQLAlchemy, loads the data into a Polars
DataFrame (up to the configured row limit), then runs the full suite of
sub-analyzers to produce a unified profile.
"""

from __future__ import annotations

import polars as pl

from app.platform.data_access import (
    SourceDataAccessError,
    fetch_source_mappings,
    validate_table_name,
)
from app.platform.logger import get_logger
from app.platform.profiling.statistics_generator import generate_statistics
from app.settings import get_settings

log = get_logger(__name__)


class ProfilerError(Exception):
    """Raised when profiling fails due to a data or query error."""


async def profile_table(table_name: str, row_limit: int | None = None) -> dict:
    """
    Profile *table_name* by reading up to *row_limit* rows (or
    ``settings.profiling_row_limit`` if not specified) and running all
    profiling sub-analyzers.

    Args:
        table_name: Fully-qualified table name, e.g. ``business_data.employees``.
                    Must reference an existing table accessible to the ``dq_app``
                    role.
        row_limit:  Optional per-request override. If None, falls back to
                    ``settings.profiling_row_limit``.

    Returns:
        A profile dict as produced by :func:`generate_statistics`.

    Raises:
        ProfilerError: If the table cannot be queried or is completely empty.
    """
    settings = get_settings()
    effective_limit = (
        row_limit
        if (row_limit is not None and row_limit > 0)
        else settings.profiling_row_limit
    )
    log.info(
        "Starting profile for '{t}' (limit={lim})", t=table_name, lim=effective_limit
    )

    # ------------------------------------------------------------------
    # Validate table name to prevent SQL injection. Source rows are read
    # through dq_executor, while profile metadata is written through dq_app.
    # ------------------------------------------------------------------
    try:
        validate_table_name(table_name)
        query = f"SELECT * FROM {table_name} LIMIT :row_limit"  # noqa: S608
        rows = await fetch_source_mappings(query, {"row_limit": effective_limit})
    except SourceDataAccessError as exc:
        raise ProfilerError(str(exc)) from exc
    except Exception as exc:
        raise ProfilerError(f"Failed to query table '{table_name}': {exc}") from exc

    if not rows:
        raise ProfilerError(f"Table '{table_name}' returned no rows.")

    # Convert list of mappings → Polars DataFrame
    df = pl.from_dicts([dict(row) for row in rows])
    log.info("Loaded {n} rows from '{t}'.", n=len(rows), t=table_name)

    return generate_statistics(df, table_name)
