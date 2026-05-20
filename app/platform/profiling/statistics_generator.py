"""
app/platform/profiling/statistics_generator.py
------------------------------------------------
Aggregates all profiling sub-analyzers into a single unified profile dict.
"""
from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from app.platform.logger import get_logger
from app.platform.profiling.distribution_analyzer import analyze_distributions
from app.platform.profiling.null_analyzer import analyze_nulls
from app.platform.profiling.schema_analyzer import analyze_schema
from app.platform.profiling.uniqueness_analyzer import analyze_uniqueness

log = get_logger(__name__)


def generate_statistics(df: pl.DataFrame, table_name: str) -> dict:
    """
    Run all profiling sub-analyzers and merge results into one profile dict.

    Args:
        df:         The Polars DataFrame containing the sampled table data.
        table_name: The source table name (included in the output for traceability).

    Returns:
        A fully-populated profile dict ready for API response or DB persistence.

    Example output structure::

        {
            "table_name": "business_data.employees",
            "row_count": 5000,
            "column_count": 6,
            "null_summary": {"salary": 2.3, "department": 0.0, ...},
            "schema_info": {"salary": "float", "department": "string", ...},
            "statistics": {"salary": {"min": 0, "max": 250000, ...}, ...},
            "uniqueness": {"employee_id": {"unique_pct": 100.0, "is_unique": true}, ...},
            "profiled_at": "2026-05-16T16:00:00.000000+00:00"
        }
    """
    log.info("Generating full statistics profile for table '{t}'.", t=table_name)

    null_summary = analyze_nulls(df)
    schema_info = analyze_schema(df)
    statistics = analyze_distributions(df)
    uniqueness = analyze_uniqueness(df)

    profile = {
        "table_name": table_name,
        "row_count": df.height,
        "column_count": df.width,
        "null_summary": null_summary,
        "schema_info": schema_info,
        "statistics": statistics,
        "uniqueness": uniqueness,
        "profiled_at": datetime.now(UTC).isoformat(),
    }

    log.info(
        "Profile ready — {rows} rows, {cols} columns.",
        rows=df.height,
        cols=df.width,
    )
    return profile
