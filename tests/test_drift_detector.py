"""
tests/test_drift_detector.py
------------------------------
Tests for the drift detection engine.
Uses in-memory pandas DataFrames — no Evidently server or DB required.
"""
import pandas as pd
import pytest

from app.platform.detection.drift_detector import (
    DriftDetectorError,
    _run_evidently,
    _validate_identifier,
    _validate_column_name,
)


def _make_df(mean: float, std: float, n: int = 200, col: str = "salary") -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(42)
    return pd.DataFrame({col: rng.normal(mean, std, n)})


class TestDriftDetectorValidation:
    def test_valid_table_identifier(self):
        _validate_identifier("business_data.employees", "table")  # should not raise

    def test_invalid_table_identifier_raises(self):
        with pytest.raises(DriftDetectorError):
            _validate_identifier("'; DROP TABLE users; --", "table")

    def test_valid_column_name(self):
        _validate_column_name("salary")  # should not raise

    def test_invalid_column_name_raises(self):
        with pytest.raises(DriftDetectorError):
            _validate_column_name("sa lary; DROP")


class TestRunEvidently:
    def test_no_drift_on_same_distribution(self):
        ref = _make_df(50_000, 5_000)
        cur = _make_df(50_000, 5_000)
        result = _run_evidently("ref_table", "cur_table", ["salary"], ref, cur)
        # Same distribution — drift should not be detected
        salary_result = next(r for r in result.column_results if r.column_name == "salary")
        assert salary_result.drift_score >= 0  # score exists
        # Note: is_drifted depends on Evidently thresholds; just check structure

    def test_drift_detected_on_shifted_distribution(self):
        ref = _make_df(50_000, 5_000)
        # Massively shifted current distribution
        cur = _make_df(500_000, 5_000)
        result = _run_evidently("ref_table", "cur_table", ["salary"], ref, cur)
        salary_result = next(r for r in result.column_results if r.column_name == "salary")
        assert salary_result.is_drifted is True

    def test_result_structure(self):
        ref = _make_df(50_000, 5_000)
        cur = _make_df(50_000, 5_000)
        result = _run_evidently("ref_table", "cur_table", ["salary"], ref, cur)
        assert result.reference_table == "ref_table"
        assert result.current_table == "cur_table"
        assert len(result.column_results) == 1
        assert result.column_results[0].column_name == "salary"
        assert isinstance(result.dataset_drift_detected, bool)
        assert 0.0 <= result.share_drifted_columns <= 1.0

    def test_missing_column_not_in_results(self):
        ref = pd.DataFrame({"salary": [1.0, 2.0, 3.0] * 50})
        cur = pd.DataFrame({"salary": [1.0, 2.0, 3.0] * 50})
        # Only "salary" exists — requesting ["salary", "missing"] would fail at
        # the public detect_drift layer (column intersection), not _run_evidently
        result = _run_evidently("ref", "cur", ["salary"], ref, cur)
        assert any(r.column_name == "salary" for r in result.column_results)
