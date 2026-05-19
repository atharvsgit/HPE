"""
app/platform/detection/drift_detector.py
------------------------------------------
Data drift detection engine using Evidently AI when available, with a small
statistical fallback for local development and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.platform.data_access import (
    SourceDataAccessError,
    fetch_source_mappings,
    validate_column_name,
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
    """Detect data drift between two source tables for selected columns."""
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

    common_cols = [
        col for col in columns if col in ref_df.columns and col in cur_df.columns
    ]
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
    """
    Run Evidently drift detection and extract per-column results.

    Evidently has version-sensitive imports on newer Python/Pydantic stacks. If
    it is unavailable or incompatible, the method falls back to a deterministic
    Kolmogorov-Smirnov based detector for numeric data so the platform and tests
    remain operational.
    """
    try:
        return _run_evidently_report(
            reference_table, current_table, columns, ref_df, cur_df
        )
    except Exception as exc:
        log.warning(
            "Evidently drift report unavailable; using statistical fallback: {e}",
            e=exc,
        )
        return _run_statistical_fallback(
            reference_table, current_table, columns, ref_df, cur_df
        )


def _run_evidently_report(
    reference_table: str,
    current_table: str,
    columns: list[str],
    ref_df: pd.DataFrame,
    cur_df: pd.DataFrame,
) -> DriftDetectionResult:
    from evidently.metrics import ColumnDriftMetric, DatasetDriftMetric  # type: ignore
    from evidently.report import Report  # type: ignore

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

    return DriftDetectionResult(
        reference_table=reference_table,
        current_table=current_table,
        columns=columns,
        column_results=column_results,
        dataset_drift_detected=dataset_drift,
        share_drifted_columns=round(share_drifted, 4),
    )


def _run_statistical_fallback(
    reference_table: str,
    current_table: str,
    columns: list[str],
    ref_df: pd.DataFrame,
    cur_df: pd.DataFrame,
) -> DriftDetectionResult:
    column_results: list[ColumnDriftResult] = []

    for column in columns:
        ref_series = ref_df[column].dropna()
        cur_series = cur_df[column].dropna()
        if ref_series.empty or cur_series.empty:
            column_results.append(
                ColumnDriftResult(
                    column_name=column,
                    stat_test="fallback_empty_column",
                    drift_score=0.0,
                    is_drifted=False,
                )
            )
            continue

        if pd.api.types.is_numeric_dtype(ref_series) and pd.api.types.is_numeric_dtype(
            cur_series
        ):
            from scipy import stats  # type: ignore[import-untyped]

            statistic, p_value = stats.ks_2samp(
                ref_series.astype(float),
                cur_series.astype(float),
            )
            column_results.append(
                ColumnDriftResult(
                    column_name=column,
                    stat_test="ks_2samp_fallback",
                    drift_score=round(float(statistic), 6),
                    is_drifted=bool(p_value < 0.05),
                )
            )
        else:
            ref_values = set(ref_series.astype(str))
            cur_values = set(cur_series.astype(str))
            union_size = max(1, len(ref_values | cur_values))
            jaccard_distance = 1 - (len(ref_values & cur_values) / union_size)
            column_results.append(
                ColumnDriftResult(
                    column_name=column,
                    stat_test="jaccard_category_fallback",
                    drift_score=round(float(jaccard_distance), 6),
                    is_drifted=bool(jaccard_distance > 0.2),
                )
            )

    drifted_count = sum(result.is_drifted for result in column_results)
    share_drifted = drifted_count / len(column_results) if column_results else 0.0

    return DriftDetectionResult(
        reference_table=reference_table,
        current_table=current_table,
        columns=columns,
        column_results=column_results,
        dataset_drift_detected=drifted_count > 0,
        share_drifted_columns=round(share_drifted, 4),
    )


def _validate_identifier(name: str, field: str) -> None:
    """Backward-compatible validation helper used by tests."""
    try:
        validate_table_name(name)
    except SourceDataAccessError as exc:
        raise DriftDetectorError(f"Invalid {field}: {exc}") from exc


def _validate_column_name(name: str) -> None:
    """Backward-compatible column validation helper used by tests."""
    try:
        validate_column_name(name)
    except SourceDataAccessError as exc:
        raise DriftDetectorError(str(exc)) from exc


async def _load_table(table_name: str, col_list: str) -> pd.DataFrame:
    """Load selected columns from a PostgreSQL table into a pandas DataFrame."""
    settings = get_settings()
    row_limit = settings.profiling_row_limit
    sql = f"SELECT {col_list} FROM {table_name} LIMIT :row_limit"  # noqa: S608
    try:
        rows = await fetch_source_mappings(sql, {"row_limit": row_limit})
        return pd.DataFrame([dict(row) for row in rows])
    except Exception as exc:
        raise DriftDetectorError(f"Failed to query '{table_name}': {exc}") from exc
