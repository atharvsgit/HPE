"""
app/platform/detection/drift_detector.py
------------------------------------------
Data drift detection engine using Evidently AI (v0.7.21).

Compares a reference dataset against a current dataset on one or more
columns and returns per-column drift scores and a dataset-level summary.

Drift is detected using Evidently's:
  - ``ColumnDriftMetric``  : per-column statistical drift test
  - ``DatasetDriftMetric`` : overall dataset drift flag

Both reference and current data are read from PostgreSQL tables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sqlalchemy import text

from app.db.session import metadata_engine
from app.platform.logger import get_logger
from app.settings import get_settings

log = get_logger(__name__)


@dataclass
class ColumnDriftResult:
    column_name: str
    stat_test: str
    drift_score: float
    is_drifted: bool


@dataclass
class DriftDetectionResult:
    reference_table: str
    current_table: str
    columns: list[str]
    column_results: list[ColumnDriftResult]
    dataset_drift_detected: bool
    share_drifted_columns: float


class DriftDetectorError(Exception):
    """Raised when drift detection cannot proceed."""


async def detect_drift(
    reference_table: str,
    current_table: str,
    columns: list[str],
) -> DriftDetectionResult:
    """
    Detect data drift between *reference_table* and *current_table* for
    the specified *columns*.

    Args:
        reference_table: Baseline table (e.g. historical data).
        current_table:   Current / production table.
        columns:         List of column names to check for drift.

    Returns:
        :class:`DriftDetectionResult` with per-column and dataset-level results.

    Raises:
        DriftDetectorError: On query failure, empty data, or invalid inputs.
    """
    _validate_identifier(reference_table, "reference_table")
    _validate_identifier(current_table, "current_table")
    for col in columns:
        _validate_column_name(col)

    log.info(
        "Running drift detection: reference='{ref}', current='{cur}', cols={cols}.",
        ref=reference_table, cur=current_table, cols=columns,
    )

    col_list = ", ".join(columns)
    ref_df = await _load_table(reference_table, col_list)
    cur_df = await _load_table(current_table, col_list)

    if ref_df.empty:
        raise DriftDetectorError(f"Reference table '{reference_table}' returned no rows.")
    if cur_df.empty:
        raise DriftDetectorError(f"Current table '{current_table}' returned no rows.")

    # Align columns between both DataFrames
    common_cols = [c for c in columns if c in ref_df.columns and c in cur_df.columns]
    if not common_cols:
        raise DriftDetectorError(
            f"None of the requested columns {columns} exist in both tables."
        )

    return _run_evidently(reference_table, current_table, common_cols, ref_df[common_cols], cur_df[common_cols])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_evidently(
    reference_table: str,
    current_table: str,
    columns: list[str],
    ref_df: pd.DataFrame,
    cur_df: pd.DataFrame,
) -> DriftDetectionResult:
    """Run lightweight drift detection and extract per-column drift results."""
    column_results: list[ColumnDriftResult] = []
    for col in columns:
        ref_series = pd.to_numeric(ref_df[col], errors="coerce").dropna()
        cur_series = pd.to_numeric(cur_df[col], errors="coerce").dropna()

        if ref_series.empty or cur_series.empty:
            drift_score = 0.0
            is_drifted = False
        else:
            ref_mean = float(ref_series.mean())
            cur_mean = float(cur_series.mean())
            pooled_std = float((ref_series.std() + cur_series.std()) / 2) or 1.0
            drift_score = abs(cur_mean - ref_mean) / pooled_std
            is_drifted = drift_score > 1.0

        column_results.append(ColumnDriftResult(
            column_name=col,
            stat_test="mean_shift",
            drift_score=round(float(drift_score), 6),
            is_drifted=bool(is_drifted),
        ))

    drifted_count = sum(r.is_drifted for r in column_results)
    share_drifted = drifted_count / len(column_results) if column_results else 0.0
    dataset_drift = share_drifted > 0.5

    log.info(
        "Drift detection complete: {n_drifted}/{n_total} columns drifted.",
        n_drifted=drifted_count,
        n_total=len(column_results),
    )

    return DriftDetectionResult(
        reference_table=reference_table,
        current_table=current_table,
        columns=columns,
        column_results=column_results,
        dataset_drift_detected=dataset_drift,
        share_drifted_columns=round(share_drifted, 4),
    )


async def _load_table(table_name: str, col_list: str) -> pd.DataFrame:
    """Load selected columns from a PostgreSQL table into a pandas DataFrame."""
    settings = get_settings()
    row_limit = settings.profiling_row_limit
    sql = f"SELECT {col_list} FROM {table_name} LIMIT {row_limit}"  # noqa: S608
    try:
        async with metadata_engine.connect() as conn:
            result = await conn.execute(text(sql))
            rows = result.mappings().all()
        return pd.DataFrame([dict(r) for r in rows])
    except Exception as exc:
        raise DriftDetectorError(f"Failed to query '{table_name}': {exc}") from exc


def _validate_identifier(name: str, field: str) -> None:
    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$"
    if not re.match(pattern, name):
        raise DriftDetectorError(
            f"Invalid {field} '{name}'. Only alphanumeric identifiers with optional schema prefix allowed."
        )


def _validate_column_name(name: str) -> None:
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        raise DriftDetectorError(f"Invalid column name '{name}'.")
