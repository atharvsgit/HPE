"""
app/platform/orchestration/dependency_manager.py
--------------------------------------------------
Declarative task dependency graph builder.

Provides a simple DAG (Directed Acyclic Graph) utility that makes
pipeline stage ordering explicit and auditable rather than hardcoded
in the flow controller.

Usage::

    from app.platform.orchestration.dependency_manager import TaskGraph

    graph = TaskGraph()
    graph.add("profile",   depends_on=[])
    graph.add("suggest",   depends_on=["profile"])
    graph.add("anomaly",   depends_on=["profile"])
    graph.add("finalize",  depends_on=["suggest", "anomaly"])

    order = graph.resolve()
    # => ["profile", "suggest", "anomaly", "finalize"]  (topological sort)
"""

from __future__ import annotations

from collections import deque

from app.platform.logger import get_logger

log = get_logger(__name__)


class CyclicDependencyError(ValueError):
    """Raised when the dependency graph contains a cycle."""


class TaskGraph:
    """
    Lightweight directed acyclic graph for declaring task execution order.

    Nodes are task names (strings). Edges represent "must run after" relationships.
    """

    def __init__(self) -> None:
        self._nodes: list[str] = []
        self._dependencies: dict[str, list[str]] = {}

    def add(self, task_name: str, depends_on: list[str] | None = None) -> None:
        """
        Register a task and its upstream dependencies.

        Args:
            task_name:  Unique task identifier string.
            depends_on: List of task names that must complete before this one.

        Raises:
            ValueError: If *task_name* is already registered.
        """
        if task_name in self._dependencies:
            raise ValueError(f"Task '{task_name}' is already registered in the graph.")
        self._nodes.append(task_name)
        self._dependencies[task_name] = depends_on or []
        log.debug("Registered task '{t}' with deps={d}.", t=task_name, d=depends_on)

    def resolve(self) -> list[str]:
        """
        Return a topologically sorted list of task names (Kahn's algorithm).

        Tasks with no dependencies come first. Tasks that depend on others
        come after all their dependencies.

        Returns:
            Ordered list of task names safe for sequential execution.

        Raises:
            CyclicDependencyError: If the graph contains a cycle.
        """
        # Fix (Copilot): Removed redundant in-degree pre-pass. Build both
        # data structures in a single clean pass, then run Kahn's BFS with
        # a deque (O(1) popleft instead of O(n) list.pop(0)).

        # For each dep → list of nodes that depend on it
        dependents: dict[str, list[str]] = {n: [] for n in self._nodes}
        for node, deps in self._dependencies.items():
            for dep in deps:
                dependents.setdefault(dep, []).append(node)

        # In-degree = number of direct dependencies
        in_degree = {n: len(self._dependencies[n]) for n in self._nodes}

        # Kahn's BFS using deque for O(1) popleft
        queue: deque[str] = deque(n for n in self._nodes if in_degree[n] == 0)
        sorted_tasks: list[str] = []

        while queue:
            node = queue.popleft()
            sorted_tasks.append(node)
            for dependent in dependents.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(sorted_tasks) != len(self._nodes):
            raise CyclicDependencyError(
                "Cycle detected in task dependency graph. "
                f"Registered: {self._nodes}, Resolved: {sorted_tasks}"
            )

        log.debug("Resolved task order: {order}.", order=sorted_tasks)
        return sorted_tasks

    def __repr__(self) -> str:
        return f"TaskGraph(tasks={self._nodes}, deps={self._dependencies})"


# ---------------------------------------------------------------------------
# Pre-built pipeline graph (the default DQ pipeline)
# ---------------------------------------------------------------------------


def build_default_pipeline_graph() -> TaskGraph:
    """
    Return the default Platform Intelligence pipeline dependency graph.

    Stages:
        profile    → validate, suggest, anomaly
        validate   → finalize
        suggest    → finalize
        anomaly    → finalize
        finalize   (terminal)

    Returns:
        A :class:`TaskGraph` instance ready for :meth:`TaskGraph.resolve`.
    """
    graph = TaskGraph()
    graph.add("profile", depends_on=[])
    graph.add("validate", depends_on=["profile"])
    graph.add("suggest", depends_on=["profile"])
    graph.add("anomaly", depends_on=["profile"])
    graph.add("finalize", depends_on=["validate", "suggest", "anomaly"])
    return graph
