"""
app/platform/profiling/uniqueness_analyzer.py
----------------------------------------------
Computes unique value count and uniqueness percentage per column.
"""
from __future__ import annotations

import polars as pl

from app.platform.logger import get_logger

log = get_logger(__name__)


def analyze_uniqueness(df: pl.DataFrame) -> dict[str, dict]:
    """
    Compute uniqueness metrics for every column in *df*.

    Returns for each column:
        - ``unique_count``: number of distinct non-null values
        - ``unique_pct``: percentage of rows that are unique (0.0 – 100.0)
        - ``is_unique``: True if all non-null values are distinct

    Args:
        df: A Polars DataFrame.

    Returns:
        Dict mapping column name → uniqueness metrics dict.
    """
    if df.is_empty():
        return {col: {"unique_count": 0, "unique_pct": 0.0, "is_unique": True}
                for col in df.columns}

    n_rows = df.height
    result: dict[str, dict] = {}

    for col in df.columns:
        series = df[col].drop_nulls()
        unique_count = series.n_unique()
        non_null_count = len(series)
        unique_pct = round((unique_count / n_rows) * 100, 4) if n_rows > 0 else 0.0
        result[col] = {
            "unique_count": unique_count,
            "unique_pct": unique_pct,
            "is_unique": unique_count == non_null_count and non_null_count == n_rows,
        }

    log.debug("Uniqueness analysis complete for {n} columns.", n=len(result))
    return result
