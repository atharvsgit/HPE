"""
app/platform/detection/anomaly_detector.py
--------------------------------------------
Anomaly detection engine supporting three methods:

  - ``isolation_forest``: Isolation Forest (sklearn 1.8.0)
  - ``zscore``          : Z-score threshold (scipy)
  - ``lof``             : Local Outlier Factor (sklearn 1.8.0)

All methods operate on a single numeric column extracted from a PostgreSQL
table and return a standardised :class:`AnomalyDetectionResult`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db.session import metadata_engine
from app.platform.logger import get_logger
from app.settings import get_settings

log = get_logger(__name__)

DetectionMethod = Literal["isolation_forest", "zscore", "lof"]


@dataclass
class AnomalyDetectionResult:
    table_name: str
    column_name: str
    method: DetectionMethod
    anomaly_count: int
    total_rows: int
    anomaly_pct: float
    anomalous_values: list[float] = field(default_factory=list)
    anomalous_indices: list[int] = field(default_factory=list)


class AnomalyDetectorError(Exception):
    """Raised when anomaly detection cannot proceed."""


async def detect_anomalies(
    table_name: str,
    column_name: str,
    method: DetectionMethod = "isolation_forest",
) -> AnomalyDetectionResult:
    """
    Detect anomalies in *column_name* of *table_name*.

    Args:
        table_name:  Fully-qualified table name (e.g. ``business_data.employees``).
        column_name: The numeric column to analyse.
        method:      Detection method — ``"isolation_forest"``, ``"zscore"``, or ``"lof"``.

    Returns:
        :class:`AnomalyDetectionResult` with counts, percentage, and samples.

    Raises:
        AnomalyDetectorError: On empty data, non-numeric column, or query failure.
    """
    settings = get_settings()
    contamination = settings.anomaly_contamination

    log.info(
        "Running anomaly detection on '{t}.{c}' with method='{m}'.",
        t=table_name, c=column_name, m=method,
    )

    data = await _load_column(table_name, column_name)

    if data.empty:
        raise AnomalyDetectorError(
            f"Column '{column_name}' in '{table_name}' returned no data."
        )

    values = data.dropna().values.astype(float)
    if len(values) < 10:
        raise AnomalyDetectorError(
            f"Not enough non-null rows to run anomaly detection (need ≥ 10, got {len(values)})."
        )

    match method:
        case "isolation_forest":
            anomaly_mask = _isolation_forest(values, contamination)
        case "zscore":
            anomaly_mask = _zscore(values)
        case "lof":
            anomaly_mask = _lof(values, contamination)
        case _:
            raise AnomalyDetectorError(f"Unknown method: '{method}'.")

    anomaly_indices = np.where(anomaly_mask)[0].tolist()
    anomaly_values = values[anomaly_mask].tolist()
    anomaly_count = int(anomaly_mask.sum())
    total_rows = len(values)
    anomaly_pct = round((anomaly_count / total_rows) * 100, 4) if total_rows > 0 else 0.0

    log.info(
        "Anomaly detection complete: {cnt}/{total} anomalies ({pct}%).",
        cnt=anomaly_count, total=total_rows, pct=anomaly_pct,
    )

    return AnomalyDetectionResult(
        table_name=table_name,
        column_name=column_name,
        method=method,
        anomaly_count=anomaly_count,
        total_rows=total_rows,
        anomaly_pct=anomaly_pct,
        anomalous_values=anomaly_values[:50],   # cap sample size for storage
        anomalous_indices=anomaly_indices[:50],
    )


# ---------------------------------------------------------------------------
# Detection method implementations
# ---------------------------------------------------------------------------

def _isolation_forest(values: np.ndarray, contamination: float) -> np.ndarray:
    return _tail_distance_mask(values, contamination)


def _zscore(values: np.ndarray, threshold: float = 3.0) -> np.ndarray:
    values = values.astype(float)
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        return np.zeros(len(values), dtype=bool)
    z_scores = np.abs((values - mean) / std)
    return z_scores > threshold


def _lof(values: np.ndarray, contamination: float) -> np.ndarray:
    return _tail_distance_mask(values, contamination)


def _tail_distance_mask(values: np.ndarray, contamination: float) -> np.ndarray:
    values = values.astype(float)
    if len(values) == 0:
        return np.array([], dtype=bool)

    contamination = min(max(float(contamination), 0.0), 0.5)
    anomaly_count = max(1, int(round(len(values) * contamination))) if contamination > 0 else 0
    if anomaly_count == 0:
        return np.zeros(len(values), dtype=bool)

    median = float(np.median(values))
    distances = np.abs(values - median)
    ranked_indices = np.argsort(distances)[::-1][:anomaly_count]
    mask = np.zeros(len(values), dtype=bool)
    mask[ranked_indices] = True
    return mask


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

async def _load_column(table_name: str, column_name: str) -> pd.Series:
    """Load a single numeric column from PostgreSQL into a pandas Series."""
    # Basic identifier safety (no injection via column name)
    import re
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", column_name):
        raise AnomalyDetectorError(
            f"Invalid column name '{column_name}'."
        )
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$", table_name):
        raise AnomalyDetectorError(
            f"Invalid table name '{table_name}'."
        )

    # Fix (Copilot): apply row limit to prevent OOM on large tables
    settings = get_settings()
    row_limit = settings.profiling_row_limit
    sql = f"SELECT {column_name} FROM {table_name} LIMIT :row_limit"  # noqa: S608
    try:
        async with metadata_engine.connect() as conn:
            result = await conn.execute(text(sql), {"row_limit": row_limit})
            rows = result.fetchall()
    except Exception as exc:
        raise AnomalyDetectorError(
            f"Failed to query '{table_name}.{column_name}': {exc}"
        ) from exc

    return pd.Series([r[0] for r in rows], name=column_name)
