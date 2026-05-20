"""
app/platform/rule_intelligence/sanitizer.py
--------------------------------------------
Rule suggestion sanitization before persistence or promotion.

This is the rule sanitizer shown in the Platform Intelligence architecture. It
sits between heuristic/Gemini suggestion engines and Atharv's rule registry so
bad SQL or malformed rule metadata never gets stored as an executable rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

from pydantic import ValidationError

from app.models.requests import ExpectedResult
from app.platform.data_access import SourceDataAccessError, validate_column_name
from app.platform.rule_intelligence.query_planner import (
    QueryPlannerError,
    validate_and_optimize,
)

ExpectedResultType = Literal[
    "zero_violations", "min_threshold", "max_threshold", "equals"
]

_ALLOWED_SUGGESTION_TYPES = {"heuristic", "gemini"}
_ALLOWED_EXPECTED_TYPES: set[str] = {
    "zero_violations",
    "min_threshold",
    "max_threshold",
    "equals",
}
_REQUIRED_KEYS = {
    "table_name",
    "column_name",
    "suggested_rule_name",
    "suggested_sql",
    "expected_result_type",
}


@dataclass(frozen=True)
class RejectedSuggestion:
    """A suggestion rejected by sanitization with the reason preserved."""

    rule_name: str
    reason: str


def sanitize_suggestions(
    suggestions: list[dict[str, Any]],
    table_name: str,
) -> tuple[list[dict[str, Any]], list[RejectedSuggestion]]:
    """
    Validate and normalize generated rule suggestions.

    Checks performed:
    - required metadata fields are present
    - suggestion belongs to the requested table
    - SQL is a safe single SELECT and satisfies Atharv's aggregate output contract
    - SQL references only the requested table
    - expected result metadata is valid for the executor
    - confidence is clamped to ``[0.0, 1.0]``
    """
    accepted: list[dict[str, Any]] = []
    rejected: list[RejectedSuggestion] = []

    for raw in suggestions:
        rule_name = str(raw.get("suggested_rule_name") or "unnamed suggestion")
        try:
            accepted.append(_sanitize_one(raw, table_name))
        except Exception as exc:
            rejected.append(RejectedSuggestion(rule_name=rule_name, reason=str(exc)))

    return accepted, rejected


def _sanitize_one(raw: dict[str, Any], table_name: str) -> dict[str, Any]:
    missing = sorted(k for k in _REQUIRED_KEYS if raw.get(k) in (None, ""))
    if missing:
        raise ValueError(f"Missing required suggestion field(s): {', '.join(missing)}")

    suggestion_table = str(raw["table_name"])
    if _normalize_table(suggestion_table) != _normalize_table(table_name):
        raise ValueError(
            f"Suggestion targets table '{suggestion_table}', expected '{table_name}'."
        )

    suggestion_type = str(raw.get("suggestion_type") or "heuristic").lower()
    if suggestion_type not in _ALLOWED_SUGGESTION_TYPES:
        raise ValueError(f"Unsupported suggestion_type '{suggestion_type}'.")

    expected_type = str(raw["expected_result_type"])
    if expected_type not in _ALLOWED_EXPECTED_TYPES:
        raise ValueError(f"Unsupported expected_result_type '{expected_type}'.")
    expected_type_typed = cast(ExpectedResultType, expected_type)

    expected_value = _coerce_expected_value(raw.get("expected_result_value"))
    try:
        ExpectedResult(type=expected_type_typed, value=expected_value)
    except ValidationError as exc:
        raise ValueError(f"Invalid expected_result metadata: {exc}") from exc

    column_name = str(raw["column_name"])
    try:
        validate_column_name(column_name)
    except SourceDataAccessError as exc:
        raise ValueError(str(exc)) from exc

    try:
        optimized_sql = validate_and_optimize(
            str(raw["suggested_sql"]),
            allowed_tables={table_name},
        )
    except QueryPlannerError as exc:
        raise ValueError(f"Invalid suggested SQL: {exc}") from exc

    return {
        "table_name": table_name,
        "column_name": column_name,
        "suggestion_type": suggestion_type,
        "suggested_rule_name": str(raw["suggested_rule_name"]),
        "suggested_sql": optimized_sql,
        "expected_result_type": expected_type_typed,
        "expected_result_value": expected_value,
        "confidence": _clamp_confidence(raw.get("confidence", 0.5)),
    }


def _coerce_expected_value(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            f"expected_result_value must be numeric, got {value!r}."
        ) from exc


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    return round(max(0.0, min(1.0, confidence)), 4)


def _normalize_table(table_name: str) -> str:
    return table_name.replace('"', "").strip().lower()
