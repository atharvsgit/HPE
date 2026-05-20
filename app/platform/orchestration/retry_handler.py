"""
app/platform/orchestration/retry_handler.py
---------------------------------------------
Retry and back-off configuration constants and helpers for Prefect tasks.

Centralises retry policy definitions so that orchestration tasks don't
scatter magic numbers throughout the codebase. Pass these as kwargs when
decorating tasks with ``@task(**retry_policy(...))``.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Immutable retry policy configuration for a Prefect task."""

    retries: int
    retry_delay_seconds: int | float
    description: str = ""


# ---------------------------------------------------------------------------
# Predefined policies
# ---------------------------------------------------------------------------

#: Default retry policy — suitable for most I/O-bound tasks.
DEFAULT_POLICY = RetryPolicy(
    retries=2,
    retry_delay_seconds=10,
    description="Default: 2 retries with 10s delay",
)

#: Aggressive retry for critical tasks (e.g., pipeline run status updates).
CRITICAL_POLICY = RetryPolicy(
    retries=4,
    retry_delay_seconds=5,
    description="Critical: 4 retries with 5s delay",
)

#: Lenient retry for slow external APIs (e.g., Gemini calls).
EXTERNAL_API_POLICY = RetryPolicy(
    retries=3,
    retry_delay_seconds=30,
    description="External API: 3 retries with 30s delay",
)

#: No retries — for tasks that must only run once (e.g., DB writes).
NO_RETRY_POLICY = RetryPolicy(
    retries=0,
    retry_delay_seconds=0,
    description="No retries",
)


def retry_kwargs(policy: RetryPolicy) -> dict:
    """
    Return a dict of Prefect ``@task`` keyword arguments for the given policy.

    Usage::

        from app.platform.orchestration.retry_handler import DEFAULT_POLICY, retry_kwargs

        @task(**retry_kwargs(DEFAULT_POLICY))
        async def my_task(): ...

    Args:
        policy: A :class:`RetryPolicy` instance.

    Returns:
        Dict suitable for unpacking into ``@task(...)`` decorator arguments.
    """
    return {
        "retries": policy.retries,
        "retry_delay_seconds": policy.retry_delay_seconds,
    }
