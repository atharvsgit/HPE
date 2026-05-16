"""
tests/test_anomaly_detector.py
--------------------------------
Tests for the anomaly detection engine.
Uses synthetic numpy arrays — no database connection required.
"""
import numpy as np
import pytest

from app.platform.detection.anomaly_detector import (
    _isolation_forest,
    _lof,
    _zscore,
)


def _clean_array(size: int = 200, n_anomalies: int = 5) -> np.ndarray:
    """Generate a mostly normal distribution with a few clear anomalies."""
    rng = np.random.default_rng(42)
    normal = rng.normal(loc=50_000, scale=5_000, size=size - n_anomalies)
    anomalies = rng.normal(loc=500_000, scale=1_000, size=n_anomalies)
    return np.concatenate([normal, anomalies])


class TestIsolationForest:
    def test_detects_known_anomalies(self):
        data = _clean_array(n_anomalies=5)
        mask = _isolation_forest(data, contamination=0.05)
        assert mask.sum() >= 1  # at least one anomaly detected
        assert mask.sum() <= len(data) * 0.15  # not flagging too many

    def test_returns_boolean_array(self):
        data = _clean_array()
        mask = _isolation_forest(data, contamination=0.05)
        assert mask.dtype == bool
        assert len(mask) == len(data)

    def test_no_anomalies_in_uniform_data(self):
        """Uniform data should have very few anomalies."""
        rng = np.random.default_rng(0)
        data = rng.uniform(0, 100, size=500)
        mask = _isolation_forest(data, contamination=0.02)
        assert mask.sum() <= 20  # ≤ 4% flagged


class TestZScore:
    def test_detects_extreme_outliers(self):
        # Add clear outliers
        data = np.concatenate([np.ones(100) * 50, np.array([1_000_000, -1_000_000])])
        mask = _zscore(data)
        assert mask[-2] is np.bool_(True)
        assert mask[-1] is np.bool_(True)

    def test_no_false_positives_on_normal_data(self):
        rng = np.random.default_rng(1)
        data = rng.normal(0, 1, size=1000)
        mask = _zscore(data)
        # Expect < 1% flagged for standard normal
        assert mask.sum() < 20

    def test_returns_correct_shape(self):
        data = np.arange(100, dtype=float)
        mask = _zscore(data)
        assert len(mask) == 100


class TestLOF:
    def test_detects_known_anomalies(self):
        data = _clean_array(n_anomalies=5)
        mask = _lof(data, contamination=0.05)
        assert mask.sum() >= 1
        assert len(mask) == len(data)

    def test_returns_boolean_array(self):
        data = _clean_array()
        mask = _lof(data, contamination=0.05)
        assert mask.dtype == bool


class TestDependencyManager:
    def test_import_succeeds(self):
        from app.platform.orchestration.dependency_manager import (
            TaskGraph,
            build_default_pipeline_graph,
        )
        assert TaskGraph is not None
        assert build_default_pipeline_graph is not None

    def test_default_graph_resolves(self):
        from app.platform.orchestration.dependency_manager import build_default_pipeline_graph
        graph = build_default_pipeline_graph()
        order = graph.resolve()
        assert "profile" in order
        assert "finalize" in order
        # profile must come before suggest and anomaly
        assert order.index("profile") < order.index("suggest")
        assert order.index("profile") < order.index("anomaly")
        # finalize must be last
        assert order[-1] == "finalize"

    def test_cycle_detection(self):
        from app.platform.orchestration.dependency_manager import (
            CyclicDependencyError,
            TaskGraph,
        )
        graph = TaskGraph()
        graph.add("a", depends_on=["b"])
        graph.add("b", depends_on=["a"])
        with pytest.raises(CyclicDependencyError):
            graph.resolve()
