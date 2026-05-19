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

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.platform.data_access import (
    SourceDataAccessError,
    fetch_source_mappings,
    validate_column_names,
    validate_table_name,
)
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
    try:
        validate_table_name(reference_table)
        validate_table_name(current_table)
        validate_column_names(columns)
    except SourceDataAccessError as exc:
        raise DriftDetectorError(str(exc)) from exc

    log.info(
        "Running drift detection: reference='{ref}', current='{cur}', cols={cols}.",
        ref=reference_table,
        cur=current_table,
        cols=columns,
    )

    col_list = ", ".join(columns)
    ref_df = await _load_table(reference_table, col_list)
    cur_df = await _load_table(current_table, col_list)

    if ref_df.empty:
        raise DriftDetectorError(
            f"Reference table '{reference_table}' returned no rows."
        )
    if cur_df.empty:
        raise DriftDetectorError(f"Current table '{current_table}' returned no rows.")

    # Align columns between both DataFrames
    common_cols = [c for c in columns if c in ref_df.columns and c in cur_df.columns]
    if not common_cols:
        raise DriftDetectorError(
            f"None of the requested columns {columns} exist in both tables."
        )

    return _run_evidently(
        reference_table,
        current_table,
        common_cols,
        ref_df[common_cols],
        cur_df[common_cols],
    )


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
    """Run Evidently report and extract per-column drift results."""
    try:
        from evidently.metrics import (  # type: ignore
            ColumnDriftMetric,
            DatasetDriftMetric,
        )
        from evidently.report import Report  # type: ignore
    except ImportError as exc:
        raise DriftDetectorError(
            "evidently is not installed. Add it to requirements.txt."
        ) from exc

    metrics = [ColumnDriftMetric(column_name=col) for col in columns]
    metrics.append(DatasetDriftMetric())

    report = Report(metrics=metrics)
    report.run(reference_data=ref_df, current_data=cur_df)
    result_dict: dict[str, Any] = report.as_dict()

    column_results: list[ColumnDriftResult] = []
    dataset_drift = False
    share_drifted = 0.0

    for metric_result in result_dict.get("metrics", []):
        metric_type = metric_result.get("metric", "")
        value = metric_result.get("result", {})

        if "ColumnDriftMetric" in metric_type:
            col_name = value.get("column_name", "unknown")
            column_results.append(
                ColumnDriftResult(
                    column_name=col_name,
                    stat_test=value.get("stattest_name", "unknown"),
                    drift_score=float(value.get("drift_score", 0.0)),
                    is_drifted=bool(value.get("drift_detected", False)),
                )
            )

        elif "DatasetDriftMetric" in metric_type:
            dataset_drift = bool(value.get("dataset_drift", False))
            share_drifted = float(value.get("share_of_drifted_columns", 0.0))

    log.info(
        "Drift detection complete: {n_drifted}/{n_total} columns drifted.",
        n_drifted=sum(r.is_drifted for r in column_results),
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
    sql = f"SELECT {col_list} FROM {table_name} LIMIT :row_limit"  # noqa: S608
    try:
        rows = await fetch_source_mappings(sql, {"row_limit": row_limit})
        return pd.DataFrame([dict(r) for r in rows])
    except Exception as exc:
        raise DriftDetectorError(f"Failed to query '{table_name}': {exc}") from exc
