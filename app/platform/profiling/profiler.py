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
from sqlalchemy import text

from app.db.session import metadata_engine
from app.platform.logger import get_logger
from app.platform.profiling.statistics_generator import generate_statistics
from app.settings import get_settings

log = get_logger(__name__)


class ProfilerError(Exception):
    """Raised when profiling fails due to a data or query error."""


async def profile_table(table_name: str) -> dict:
    """
    Profile *table_name* by reading up to ``settings.profiling_row_limit`` rows
    and running all profiling sub-analyzers.

    Args:
        table_name: Fully-qualified table name, e.g. ``business_data.employees``.
                    Must reference an existing table accessible to the ``dq_app``
                    role.

    Returns:
        A profile dict as produced by :func:`generate_statistics`.

    Raises:
        ProfilerError: If the table cannot be queried or is completely empty.
    """
    settings = get_settings()
    row_limit = settings.profiling_row_limit
    log.info("Starting profile for '{t}' (limit={lim})", t=table_name, lim=row_limit)

    # ------------------------------------------------------------------
    # Validate table name to prevent SQL injection.
    # We only allow schema.table or bare table identifiers.
    # ------------------------------------------------------------------
    _validate_table_name(table_name)

    query = f"SELECT * FROM {table_name} LIMIT {row_limit}"  # noqa: S608

    try:
        async with metadata_engine.connect() as conn:
            result = await conn.execute(text(query))
            rows = result.mappings().all()
    except Exception as exc:
        raise ProfilerError(
            f"Failed to query table '{table_name}': {exc}"
        ) from exc

    if not rows:
        raise ProfilerError(f"Table '{table_name}' returned no rows.")

    # Convert list of mappings → Polars DataFrame
    df = pl.from_dicts([dict(row) for row in rows])
    log.info("Loaded {n} rows from '{t}'.", n=len(rows), t=table_name)

    return generate_statistics(df, table_name)


def _validate_table_name(table_name: str) -> None:
    """
    Ensure the table name only contains alphanumeric characters, underscores,
    and at most one dot (schema separator).

    Raises:
        ProfilerError: On invalid identifier.
    """
    import re

    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$"
    if not re.match(pattern, table_name):
        raise ProfilerError(
            f"Invalid table name '{table_name}'. "
            "Only alphanumeric characters, underscores, and one optional "
            "schema separator (.) are allowed."
        )
