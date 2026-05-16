"""
app/platform/profiling/schema_analyzer.py
------------------------------------------
Detects column data types and maps Polars dtypes to human-readable strings.
"""
from __future__ import annotations

import polars as pl

from app.platform.logger import get_logger

log = get_logger(__name__)

# Map from Polars dtype base class names to simpler readable labels.
_DTYPE_MAP: dict[str, str] = {
    "Int8": "integer",
    "Int16": "integer",
    "Int32": "integer",
    "Int64": "integer",
    "UInt8": "integer",
    "UInt16": "integer",
    "UInt32": "integer",
    "UInt64": "integer",
    "Float32": "float",
    "Float64": "float",
    "Decimal": "decimal",
    "Boolean": "boolean",
    "Utf8": "string",
    "String": "string",
    "Date": "date",
    "Datetime": "datetime",
    "Duration": "duration",
    "Time": "time",
    "List": "list",
    "Struct": "struct",
    "Null": "null",
    "Categorical": "categorical",
    "Enum": "enum",
}


def analyze_schema(df: pl.DataFrame) -> dict[str, str]:
    """
    Map each column to a human-readable data type label.

    Args:
        df: A Polars DataFrame.

    Returns:
        A dict mapping column name → readable dtype string.
        Unknown types fall back to the raw Polars dtype repr.
    """
    result: dict[str, str] = {}
    for col, dtype in zip(df.columns, df.dtypes):
        base_name = type(dtype).__name__
        readable = _DTYPE_MAP.get(base_name, str(dtype))
        result[col] = readable

    log.debug("Schema analysis complete for {n} columns.", n=len(result))
    return result
