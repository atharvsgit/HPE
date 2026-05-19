"""
app/platform/data_access.py
---------------------------
Read-only source data access helpers for the Platform Intelligence layer.

The platform stores metadata through ``dq_app``/``metadata_engine``, but source
business data should be read through Atharv's restricted ``dq_executor`` role.
That role has SELECT-only access to ``business_data`` and is used here inside a
read-only transaction with the configured statement timeout.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import text

from app.settings import get_settings

_TABLE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$")
_COLUMN_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class SourceDataAccessError(Exception):
    """Raised when source data cannot be queried safely."""


def validate_table_name(table_name: str) -> None:
    """Validate a bare or schema-qualified table identifier."""
    if not _TABLE_RE.match(table_name):
        raise SourceDataAccessError(
            f"Invalid table name '{table_name}'. Only alphanumeric identifiers "
            "with one optional schema separator are allowed."
        )


def validate_column_name(column_name: str) -> None:
    """Validate a single column identifier."""
    if not _COLUMN_RE.match(column_name):
        raise SourceDataAccessError(
            f"Invalid column name '{column_name}'. Only alphanumeric identifiers are allowed."
        )


def validate_column_names(column_names: Sequence[str]) -> None:
    """Validate a non-empty list of column identifiers."""
    if not column_names:
        raise SourceDataAccessError("At least one column name is required.")
    for column_name in column_names:
        validate_column_name(column_name)


async def fetch_source_mappings(
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    """Execute a source SELECT statement and return mapping rows."""
    from app.db.session import executor_engine

    async with executor_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text(_statement_timeout_sql()))
            result = await conn.execute(text(sql), dict(params or {}))
            return cast(list[Mapping[str, Any]], list(result.mappings().all()))


async def fetch_source_rows(
    sql: str,
    params: Mapping[str, Any] | None = None,
) -> list[Any]:
    """Execute a source SELECT statement and return positional rows."""
    from app.db.session import executor_engine

    async with executor_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text(_statement_timeout_sql()))
            result = await conn.execute(text(sql), dict(params or {}))
            return list(result.fetchall())


def _statement_timeout_sql() -> str:
    settings = get_settings()
    # statement_timeout_ms is parsed as int by Settings, so this formatted SQL
    # does not contain user-controlled text.
    return f"SET LOCAL statement_timeout = '{settings.statement_timeout_ms}ms'"
