from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

try:
    import sqlglot
    import sqlglot.errors
except ImportError:  # pragma: no cover - production images install sqlglot.
    sqlglot = None

from app.daemon.sql_safety import strip_trailing_semicolon


def build_rule_fingerprint(
    *,
    database_connection_id: int | None,
    sql: str,
    expected_result_type: str,
    expected_result_value: Any,
) -> str:
    payload = {
        "database_connection_id": database_connection_id,
        "sql": normalize_rule_sql(sql),
        "expected_result": {
            "type": expected_result_type,
            "value": _normalize_decimal(expected_result_value),
        },
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def normalize_rule_sql(sql: str) -> str:
    stripped = strip_trailing_semicolon(sql)
    if sqlglot is None:
        return _fallback_normalize_sql(stripped)

    try:
        statements = sqlglot.parse(stripped, read="postgres")
    except sqlglot.errors.ParseError:
        return _fallback_normalize_sql(stripped)

    if len(statements) != 1 or statements[0] is None:
        return _fallback_normalize_sql(stripped)

    return statements[0].sql(dialect="postgres", pretty=False).strip()


def _normalize_decimal(value: Any) -> str | None:
    if value is None:
        return None
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    return format(decimal_value.normalize(), "f")


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _fallback_normalize_sql(value: str) -> str:
    return _casefold_unquoted(_collapse_whitespace(value))


def _casefold_unquoted(value: str) -> str:
    output: list[str] = []
    index = 0
    quote: str | None = None

    while index < len(value):
        char = value[index]
        next_char = value[index + 1] if index + 1 < len(value) else ""

        if char in {"'", '"'}:
            output.append(char)
            if quote is None:
                quote = char
            elif quote == char:
                if char == "'" and next_char == "'":
                    output.append(next_char)
                    index += 1
                else:
                    quote = None
        elif quote is None:
            output.append(char.lower())
        else:
            output.append(char)

        index += 1

    return "".join(output)
