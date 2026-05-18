from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.db.session import executor_engine
from app.models.requests import DatabaseConnectionRequest
from app.models.responses import DatabaseConnectionResponse

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _split_table_name(table_name: str) -> tuple[str, str]:
    parts = [part.strip() for part in table_name.split(".") if part.strip()]
    if len(parts) == 1:
        schema, table = "business_data", parts[0]
    elif len(parts) == 2:
        schema, table = parts
    else:
        raise ValueError("Table must be provided as table or schema.table.")

    if not _IDENTIFIER_RE.match(schema) or not _IDENTIFIER_RE.match(table):
        raise ValueError("Table name may only contain letters, numbers, and underscores.")

    return schema, table


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


async def connect_database(request: DatabaseConnectionRequest) -> DatabaseConnectionResponse:
    table_input = str(request.config.get("table") or "").strip()
    if not table_input:
        raise ValueError("A target table is required.")

    schema_name, table_name = _split_table_name(table_input)
    qualified_table = f"{_quote_identifier(schema_name)}.{_quote_identifier(table_name)}"

    async with executor_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            table_exists = await conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = :schema_name
                          AND table_name = :table_name
                    )
                    """
                ),
                {"schema_name": schema_name, "table_name": table_name},
            )

            if not table_exists.scalar_one():
                raise ValueError(f"Table {schema_name}.{table_name} was not found.")

            columns_result = await conn.execute(
                text(
                    """
                    SELECT
                        column_name,
                        data_type,
                        is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = :schema_name
                      AND table_name = :table_name
                    ORDER BY ordinal_position
                    """
                ),
                {"schema_name": schema_name, "table_name": table_name},
            )
            row_count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {qualified_table}"))
            columns_rows = columns_result.mappings().all()
            row_count = int(row_count_result.scalar_one())

    columns = [
        {
            "columnName": row["column_name"],
            "dataType": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
        }
        for row in columns_rows
    ]

    database_name = str(request.config.get("database") or "dq_test")
    return DatabaseConnectionResponse(
        dataset={
            "id": f"{schema_name}.{table_name}",
            "name": f"{schema_name}.{table_name}",
            "table": f"{schema_name}.{table_name}",
            "tableName": f"{schema_name}.{table_name}",
            "database": database_name,
            "sourceType": "database",
            "subType": "postgresql",
            "records": row_count,
        },
        schema=columns,
        rows=[],
        message=f"Connected to {schema_name}.{table_name} with {row_count} rows.",
    )
