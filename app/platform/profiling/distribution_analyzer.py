"""
app/platform/profiling/distribution_analyzer.py
-------------------------------------------------
Computes value distribution statistics for numeric and string columns.
"""
from __future__ import annotations

import polars as pl

from app.platform.logger import get_logger

log = get_logger(__name__)

_NUMERIC_DTYPES = {
    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
    pl.Float32, pl.Float64,
}


def _is_numeric(dtype) -> bool:
    return type(dtype) in _NUMERIC_DTYPES


def analyze_distributions(df: pl.DataFrame) -> dict[str, dict]:
    """
    Compute distribution statistics per column.

    For numeric columns returns:
        min, max, mean, std, median, p25, p75

    For string/categorical columns returns:
        top_values: list of {value, count} dicts (up to 10 most frequent)

    Args:
        df: A Polars DataFrame.

    Returns:
        A dict mapping column name → stats dict.
    """
    result: dict[str, dict] = {}

    for col in df.columns:
        series = df[col].drop_nulls()
        dtype = df[col].dtype

        if series.is_empty():
            result[col] = {"note": "all_null"}
            continue

        if _is_numeric(dtype):
            try:
                result[col] = {
                    "min": _safe_float(series.min()),
                    "max": _safe_float(series.max()),
                    "mean": _safe_float(series.mean()),
                    "std": _safe_float(series.std()),
                    "median": _safe_float(series.median()),
                    "p25": _safe_float(series.quantile(0.25, interpolation="nearest")),
                    "p75": _safe_float(series.quantile(0.75, interpolation="nearest")),
                }
            except Exception as exc:
                result[col] = {"error": str(exc)}
        else:
            # String / categorical: top value counts
            try:
                vc = (
                    series.cast(pl.String)
                    .value_counts()
                    .sort("count", descending=True)
                    .head(10)
                )
                result[col] = {
                    "top_values": [
                        {"value": row[col], "count": row["count"]}
                        for row in vc.iter_rows(named=True)
                    ]
                }
            except Exception as exc:
                result[col] = {"error": str(exc)}

    log.debug("Distribution analysis complete for {n} columns.", n=len(result))
    return result


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
