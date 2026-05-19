"""
app/platform/rule_intelligence/query_planner.py
-------------------------------------------------
SQL compilation and optimization layer using SQLGlot (v30.8.0).

Responsibilities:
  1. Validate that a SQL string is a safe, parseable SELECT statement.
  2. Transpile / pretty-print SQL into canonical PostgreSQL form.
  3. Compile a high-level rule config dict into a ready-to-run SQL string.

This sits between the rule suggestion engines and the executor — every
suggestion's SQL is run through the planner before being saved as a rule.
"""

from __future__ import annotations

import re
from typing import Any

import sqlglot
import sqlglot.errors
from sqlglot import exp

from app.daemon.sql_safety import SQLSafetyError, validate_safe_select
from app.platform.data_access import validate_column_name, validate_table_name
from app.platform.logger import get_logger

log = get_logger(__name__)

# Allowed output column names (as per Atharv's SQL contract)
_ALLOWED_OUTPUT_COLUMNS = {"violation_count", "observed_value"}

# Supported rule config types for compile_rule_to_sql
_RULE_TYPES = {
    "null_check",
    "not_null_required",
    "uniqueness_check",
    "min_value",
    "max_value",
    "range_check",
    "row_count_min",
    "row_count_max",
}


class QueryPlannerError(ValueError):
    """Raised when SQL fails validation or compilation."""


def validate_and_optimize(
    sql: str,
    dialect: str = "postgres",
    allowed_tables: set[str] | None = None,
) -> str:
    """
    Parse, validate, and optimize a SQL string using SQLGlot.

    Ensures:
    - The statement is a SELECT (not DDL/DML).
    - The statement produces exactly one output column named
      ``violation_count`` or ``observed_value``.
    - The SQL is safe and parses without errors.

    Args:
        sql:     Raw SQL string from a rule suggestion or user input.
        dialect: Target SQL dialect (default: ``"postgres"``).

    Returns:
        Canonicalized, pretty-printed SQL string.

    Raises:
        QueryPlannerError: On parse failures or contract violations.
    """
    try:
        validate_safe_select(sql)
    except SQLSafetyError as exc:
        raise QueryPlannerError(str(exc)) from exc

    try:
        statements = sqlglot.parse(sql, dialect=dialect)
    except sqlglot.errors.ParseError as exc:
        raise QueryPlannerError(f"SQL parse error: {exc}") from exc

    if not statements or statements[0] is None:
        raise QueryPlannerError("SQL string produced no parseable statements.")

    if len(statements) > 1:
        raise QueryPlannerError("Only a single SQL statement is allowed.")

    stmt = statements[0]
    if not isinstance(stmt, exp.Select):
        raise QueryPlannerError("Only SELECT statements are allowed.")

    # Validate output column contract and optional table allowlist.
    _assert_valid_output_column(stmt)
    if allowed_tables is not None:
        _assert_allowed_tables(stmt, allowed_tables)

    # Transpile to canonical PostgreSQL form
    optimized_sql: str = stmt.sql(dialect=dialect, pretty=True)
    log.debug("SQL validated and optimized via SQLGlot.")
    return optimized_sql


def compile_rule_to_sql(rule_config: dict[str, Any]) -> str:
    """
    Compile a high-level rule config dict into a PostgreSQL SELECT string.

    The generated SQL always returns a single row with one column named
    ``violation_count``.

    Args:
        rule_config: A dict with at minimum:
            - ``table`` (str): fully-qualified table name
            - ``column`` (str): column to check (not used for table-level rules)
            - ``rule_type`` (str): one of the types in ``_RULE_TYPES``
            - Additional params depending on rule_type:
              - ``min_value`` (float) for ``min_value`` / ``range_check``
              - ``max_value`` (float) for ``max_value`` / ``range_check``
              - ``row_count_min`` (int) for ``row_count_min``
              - ``row_count_max`` (int) for ``row_count_max``

    Returns:
        A ready-to-use SELECT SQL string.

    Raises:
        QueryPlannerError: On missing params or unsupported rule_type.
    """
    rule_type = rule_config.get("rule_type")
    table = rule_config.get("table", "")
    column = rule_config.get("column", "")

    if rule_type not in _RULE_TYPES:
        raise QueryPlannerError(
            f"Unsupported rule_type '{rule_type}'. "
            f"Supported types: {sorted(_RULE_TYPES)}"
        )
    if not table:
        raise QueryPlannerError("rule_config must include a non-empty 'table' field.")
    try:
        validate_table_name(table)
    except Exception as exc:
        raise QueryPlannerError(str(exc)) from exc

    # Fix (Copilot): validate column is present for all column-level rule types
    _COLUMN_REQUIRED_TYPES = {
        "null_check",
        "not_null_required",
        "uniqueness_check",
        "min_value",
        "max_value",
        "range_check",
    }
    if rule_type in _COLUMN_REQUIRED_TYPES and not column:
        raise QueryPlannerError(
            f"rule_type '{rule_type}' requires a non-empty 'column' field."
        )
    if column:
        try:
            validate_column_name(column)
        except Exception as exc:
            raise QueryPlannerError(str(exc)) from exc

    sql = _build_sql(rule_type, table, column, rule_config)
    log.debug("Compiled rule_type='{t}' to SQL.", t=rule_type)
    return sql


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _assert_valid_output_column(stmt: exp.Select) -> None:
    """
    Check that the SELECT has exactly one output column and that it is aliased
    to ``violation_count`` or ``observed_value``.
    """
    selections = stmt.expressions
    if len(selections) != 1:
        raise QueryPlannerError(
            f"SELECT must have exactly one output column; found {len(selections)}."
        )

    col_expr = selections[0]
    # Walk the expression to find the alias
    alias = None
    if isinstance(col_expr, exp.Alias):
        alias = col_expr.alias
    else:
        # No alias — check if the bare column name matches
        if isinstance(col_expr, exp.Column):
            alias = col_expr.name

    if alias not in _ALLOWED_OUTPUT_COLUMNS:
        raise QueryPlannerError(
            f"Output column must be named one of {_ALLOWED_OUTPUT_COLUMNS}; "
            f"got '{alias}'."
        )


def extract_table_names(sql: str, dialect: str = "postgres") -> set[str]:
    """Return table names referenced by a single safe SELECT statement."""
    try:
        validate_safe_select(sql)
        statements = sqlglot.parse(sql, dialect=dialect)
    except (SQLSafetyError, sqlglot.errors.ParseError) as exc:
        raise QueryPlannerError(str(exc)) from exc
    if (
        not statements
        or len(statements) != 1
        or not isinstance(statements[0], exp.Select)
    ):
        raise QueryPlannerError("Only a single SELECT statement is allowed.")
    return _referenced_tables(statements[0])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _assert_allowed_tables(stmt: exp.Select, allowed_tables: set[str]) -> None:
    referenced = _referenced_tables(stmt)
    if not referenced:
        raise QueryPlannerError("SQL must reference the target dataset table.")

    allowed = _normalized_table_names(allowed_tables)
    disallowed = sorted(
        t for t in referenced if _normalize_table_name(t) not in allowed
    )
    if disallowed:
        raise QueryPlannerError(
            f"SQL references table(s) outside the allowed set: {disallowed}."
        )


def _referenced_tables(stmt: exp.Select) -> set[str]:
    tables: set[str] = set()
    for table in stmt.find_all(exp.Table):
        parts: list[str] = []
        db = table.args.get("db")
        if db is not None:
            parts.append(str(db).strip('"'))
        name = table.name
        if name:
            parts.append(name.strip('"'))
        if parts:
            tables.add(".".join(parts))
    return tables


def _normalized_table_names(table_names: set[str]) -> set[str]:
    normalized: set[str] = set()
    for table_name in table_names:
        normalized.add(_normalize_table_name(table_name))
        if "." in table_name:
            normalized.add(_normalize_table_name(table_name.split(".")[-1]))
    return normalized


def _normalize_table_name(table_name: str) -> str:
    return re.sub(r'"', "", table_name).lower()


def _build_sql(rule_type: str, table: str, column: str, cfg: dict[str, Any]) -> str:
    """Build a SQL string for the given rule type."""
    match rule_type:
        case "null_check" | "not_null_required":
            return (
                f"SELECT COUNT(*) AS violation_count "
                f"FROM {table} WHERE {column} IS NULL"
            )
        case "uniqueness_check":
            return (
                f"SELECT COUNT(*) - COUNT(DISTINCT {column}) AS violation_count "
                f"FROM {table}"
            )
        case "min_value":
            min_val = _require_param(cfg, "min_value")
            return (
                f"SELECT COUNT(*) AS violation_count "
                f"FROM {table} WHERE {column} < {min_val}"
            )
        case "max_value":
            max_val = _require_param(cfg, "max_value")
            return (
                f"SELECT COUNT(*) AS violation_count "
                f"FROM {table} WHERE {column} > {max_val}"
            )
        case "range_check":
            min_val = _require_param(cfg, "min_value")
            max_val = _require_param(cfg, "max_value")
            return (
                f"SELECT COUNT(*) AS violation_count "
                f"FROM {table} WHERE {column} < {min_val} OR {column} > {max_val}"
            )
        case "row_count_min" | "row_count_max":
            # Fix (Copilot): row_count_min/max thresholds are evaluated by the
            # executor using expected_result_value (min_threshold / max_threshold).
            # The SQL simply reports the observed row count; the caller sets
            # expected_result_type and expected_result_value accordingly.
            return f"SELECT COUNT(*) AS observed_value FROM {table}"
        case _:
            raise QueryPlannerError(f"Unhandled rule_type: '{rule_type}'")


def _require_param(cfg: dict[str, Any], key: str) -> Any:
    if key not in cfg or cfg[key] is None:
        raise QueryPlannerError(f"rule_config is missing required parameter '{key}'.")
    return cfg[key]
