"""
tests/test_flow_controller.py
-------------------------------
Tests for the Prefect orchestration flow controller.
Uses Prefect's `.fn()` pattern to run flows/tasks as plain Python
functions without requiring a Prefect server.
"""

import pytest

from app.platform.orchestration.dependency_manager import (
    CyclicDependencyError,
    TaskGraph,
    build_default_pipeline_graph,
)
from app.platform.orchestration.flow_controller import run_full_pipeline
from app.platform.orchestration.retry_handler import (
    CRITICAL_POLICY,
    DEFAULT_POLICY,
    EXTERNAL_API_POLICY,
    NO_RETRY_POLICY,
    retry_kwargs,
)


class TestRetryHandler:
    def test_default_policy_has_retries(self):
        assert DEFAULT_POLICY.retries == 2
        assert DEFAULT_POLICY.retry_delay_seconds == 10

    def test_critical_policy_has_more_retries(self):
        assert CRITICAL_POLICY.retries > DEFAULT_POLICY.retries

    def test_no_retry_policy_has_zero_retries(self):
        assert NO_RETRY_POLICY.retries == 0

    def test_retry_kwargs_returns_dict(self):
        kwargs = retry_kwargs(DEFAULT_POLICY)
        assert "retries" in kwargs
        assert "retry_delay_seconds" in kwargs
        assert kwargs["retries"] == 2

    def test_external_api_policy_has_long_delay(self):
        assert EXTERNAL_API_POLICY.retry_delay_seconds >= 30


class TestDependencyManager:
    def test_default_pipeline_graph_resolves(self):
        graph = build_default_pipeline_graph()
        order = graph.resolve()
        assert len(order) == 5
        assert order[0] == "profile"
        assert "validate" in order
        assert order[-1] == "finalize"

    def test_profile_before_suggest(self):
        graph = build_default_pipeline_graph()
        order = graph.resolve()
        assert order.index("profile") < order.index("suggest")

    def test_profile_before_anomaly(self):
        graph = build_default_pipeline_graph()
        order = graph.resolve()
        assert order.index("profile") < order.index("anomaly")

    def test_parallel_stages_before_finalize(self):
        graph = build_default_pipeline_graph()
        order = graph.resolve()
        assert order.index("validate") < order.index("finalize")
        assert order.index("suggest") < order.index("finalize")
        assert order.index("anomaly") < order.index("finalize")

    def test_duplicate_task_raises(self):
        graph = TaskGraph()
        graph.add("a")
        with pytest.raises(ValueError, match="already registered"):
            graph.add("a")

    def test_cycle_detection_raises(self):
        graph = TaskGraph()
        graph.add("x", depends_on=["y"])
        graph.add("y", depends_on=["x"])
        with pytest.raises(CyclicDependencyError):
            graph.resolve()

    def test_single_node_graph(self):
        graph = TaskGraph()
        graph.add("only_task")
        order = graph.resolve()
        assert order == ["only_task"]

    def test_custom_pipeline_order(self):
        graph = TaskGraph()
        graph.add("ingest", depends_on=[])
        graph.add("profile", depends_on=["ingest"])
        graph.add("validate", depends_on=["profile"])
        graph.add("report", depends_on=["validate"])
        order = graph.resolve()
        assert order == ["ingest", "profile", "validate", "report"]


class TestFlowImport:
    def test_flow_is_importable(self):
        """Verify the flow can be imported without starting a Prefect server."""
        assert run_full_pipeline is not None

    def test_flow_has_fn_attribute(self):
        """Verify Prefect decorated the flow and .fn is accessible for testing."""
        assert hasattr(run_full_pipeline, "fn")
