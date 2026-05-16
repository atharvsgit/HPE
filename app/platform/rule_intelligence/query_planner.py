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

import sqlglot
import sqlglot.errors
from sqlglot import exp

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


def validate_and_optimize(sql: str, dialect: str = "postgres") -> str:
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

    # Validate output column contract
    _assert_valid_output_column(stmt)

    # Transpile to canonical PostgreSQL form
    optimized_sql: str = stmt.sql(dialect=dialect, pretty=True)
    log.debug("SQL validated and optimized via SQLGlot.")
    return optimized_sql


def compile_rule_to_sql(rule_config: dict) -> str:
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


def _build_sql(rule_type: str, table: str, column: str, cfg: dict) -> str:
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
        case "row_count_min":
            min_count = _require_param(cfg, "row_count_min")
            return f"SELECT COUNT(*) AS observed_value FROM {table}"
        case "row_count_max":
            max_count = _require_param(cfg, "row_count_max")
            return f"SELECT COUNT(*) AS observed_value FROM {table}"
        case _:
            raise QueryPlannerError(f"Unhandled rule_type: '{rule_type}'")


def _require_param(cfg: dict, key: str):
    if key not in cfg or cfg[key] is None:
        raise QueryPlannerError(f"rule_config is missing required parameter '{key}'.")
    return cfg[key]
