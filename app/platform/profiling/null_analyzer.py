"""
app/platform/profiling/null_analyzer.py
----------------------------------------
Analyzes null/missing value counts per column using Polars.
"""
from __future__ import annotations

import polars as pl

from app.platform.logger import get_logger

log = get_logger(__name__)


def analyze_nulls(df: pl.DataFrame) -> dict[str, float]:
    """
    Compute the null percentage for every column in *df*.

    Args:
        df: A Polars DataFrame.

    Returns:
        A dict mapping column name → null percentage (0.0 – 100.0).
        Returns 0.0 for all columns when the DataFrame is empty.
    """
    if df.is_empty():
        log.warning("DataFrame is empty; returning zero null percentages.")
        return {col: 0.0 for col in df.columns}

    n_rows = df.height
    result: dict[str, float] = {}

    for col in df.columns:
        null_count = df[col].null_count()
        pct = round((null_count / n_rows) * 100, 4)
        result[col] = pct

    log.debug("Null analysis complete for {n} columns.", n=len(result))
    return result
