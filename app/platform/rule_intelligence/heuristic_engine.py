"""
app/platform/rule_intelligence/heuristic_engine.py
----------------------------------------------------
Generates data quality rule suggestions purely from a dataset profile
without any external API calls. Works offline and is always available
as a fallback regardless of whether a Gemini API key is configured.

Heuristic rules produced:
  - null_check          : flag when null% > 0 (zero_violations or max_threshold)
  - not_null_required   : flag when null% == 0 (enforce strictly)
  - uniqueness_check    : flag when column appears to be a key (unique_pct ≈ 100%)
  - numeric_range_check : flag values outside [min, max] range for numeric cols
  - category_check      : flag values outside observed set for low-cardinality strings
"""
from __future__ import annotations

from app.platform.logger import get_logger

log = get_logger(__name__)

# Thresholds
_MAX_CATEGORY_UNIQUE = 20       # columns with ≤ this many unique values get category check
_UNIQUENESS_KEY_THRESHOLD = 98  # columns with ≥ this unique_pct are treated as keys
_NULL_WARN_THRESHOLD = 5.0      # null% above this triggers a max_threshold suggestion


def suggest_rules(profile: dict, table_name: str) -> list[dict]:
    """
    Analyse *profile* and return a list of rule suggestion dicts.

    Args:
        profile:    Profile dict produced by :func:`~app.platform.profiling.profiler.profile_table`.
        table_name: Fully-qualified table name, used to build SQL.

    Returns:
        List of suggestion dicts, each containing:
        ``column_name``, ``suggestion_type``, ``suggested_rule_name``,
        ``suggested_sql``, ``expected_result_type``,
        ``expected_result_value``, ``confidence``.
    """
    suggestions: list[dict] = []

    null_summary: dict[str, float] = profile.get("null_summary", {})
    uniqueness: dict[str, dict] = profile.get("uniqueness", {})
    statistics: dict[str, dict] = profile.get("statistics", {})
    schema_info: dict[str, str] = profile.get("schema_info", {})

    for col in null_summary:
        null_pct = null_summary[col]
        dtype = schema_info.get(col, "unknown")
        unique_info = uniqueness.get(col, {})
        stats = statistics.get(col, {})

        # ----------------------------------------------------------------
        # 1. NULL checks
        # ----------------------------------------------------------------
        if null_pct == 0.0:
            suggestions.append(_make_suggestion(
                col=col,
                table=table_name,
                rule_name=f"{col} must not contain nulls",
                sql=f"SELECT COUNT(*) AS violation_count FROM {table_name} WHERE {col} IS NULL",
                result_type="zero_violations",
                result_value=None,
                confidence=0.95,
            ))
        elif 0 < null_pct <= _NULL_WARN_THRESHOLD:
            # Allow at most (null_pct * row_count / 100) nulls — approximate ceiling
            max_allowed = max(1, int((null_pct / 100) * profile.get("row_count", 1000) * 1.1))
            suggestions.append(_make_suggestion(
                col=col,
                table=table_name,
                rule_name=f"{col} null count within acceptable limit",
                sql=f"SELECT COUNT(*) AS violation_count FROM {table_name} WHERE {col} IS NULL",
                result_type="max_threshold",
                result_value=float(max_allowed),
                confidence=0.75,
            ))

        # ----------------------------------------------------------------
        # 2. Uniqueness / key checks
        # ----------------------------------------------------------------
        unique_pct = unique_info.get("unique_pct", 0)
        if unique_pct >= _UNIQUENESS_KEY_THRESHOLD:
            suggestions.append(_make_suggestion(
                col=col,
                table=table_name,
                rule_name=f"{col} must be unique (no duplicates)",
                sql=(
                    f"SELECT COUNT(*) - COUNT(DISTINCT {col}) AS violation_count "
                    f"FROM {table_name}"
                ),
                result_type="zero_violations",
                result_value=None,
                confidence=0.9,
            ))

        # ----------------------------------------------------------------
        # 3. Numeric range checks
        # ----------------------------------------------------------------
        if dtype in ("integer", "float", "decimal") and "min" in stats and "max" in stats:
            col_min = stats.get("min")
            col_max = stats.get("max")
            if col_min is not None and col_max is not None and col_min != col_max:
                suggestions.append(_make_suggestion(
                    col=col,
                    table=table_name,
                    rule_name=f"{col} values within observed range [{col_min}, {col_max}]",
                    sql=(
                        f"SELECT COUNT(*) AS violation_count FROM {table_name} "
                        f"WHERE {col} < {col_min} OR {col} > {col_max}"
                    ),
                    result_type="zero_violations",
                    result_value=None,
                    confidence=0.7,
                ))

        # ----------------------------------------------------------------
        # 4. Low-cardinality category check
        # ----------------------------------------------------------------
        unique_count = unique_info.get("unique_count", 0)
        if dtype in ("string", "categorical") and 2 <= unique_count <= _MAX_CATEGORY_UNIQUE:
            top_values = stats.get("top_values", [])
            if top_values:
                # Fix (Copilot): escape single quotes in string values to prevent
                # SQL injection / syntax errors (e.g. O'Reilly → O''Reilly)
                def _escape(v: str) -> str:
                    return v.replace("'", "''")

                categories = ", ".join(
                    f"'{_escape(str(v['value']))}'" for v in top_values if v.get("value") is not None
                )
                if categories:
                    suggestions.append(_make_suggestion(
                        col=col,
                        table=table_name,
                        rule_name=f"{col} contains only known categories",
                        sql=(
                            f"SELECT COUNT(*) AS violation_count FROM {table_name} "
                            f"WHERE {col} NOT IN ({categories})"
                        ),
                        result_type="zero_violations",
                        result_value=None,
                        confidence=0.8,
                    ))

    log.info(
        "Heuristic engine produced {n} suggestions for '{t}'.",
        n=len(suggestions),
        t=table_name,
    )
    return suggestions


def _make_suggestion(
    col: str,
    table: str,
    rule_name: str,
    sql: str,
    result_type: str,
    result_value: float | None,
    confidence: float,
) -> dict:
    return {
        "column_name": col,
        "table_name": table,
        "suggestion_type": "heuristic",
        "suggested_rule_name": rule_name,
        "suggested_sql": sql,
        "expected_result_type": result_type,
        "expected_result_value": result_value,
        "confidence": round(confidence, 4),
    }
