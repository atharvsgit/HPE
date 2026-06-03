from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.db.session import executor_engine, metadata_engine
from app.models.product import (
    ColumnInfo,
    DatabaseConnectionCreate,
    DatabaseConnectionResponse,
    DatabaseSchemaResponse,
    DatabaseTestResponse,
    TableInfo,
)
from app.settings import get_settings


def _engine_from_config(row: dict[str, Any]) -> AsyncEngine:
    settings = get_settings()
    username = quote_plus(str(row["username"]))
    password = quote_plus(str(row["password_secret"]))
    host = row["host"]
    port = int(row["port"])
    database = row["database_name"]
    url = f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"
    return create_async_engine(
        url,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout,
        pool_recycle=settings.pool_recycle,
        pool_pre_ping=True,
    )


@asynccontextmanager
async def target_engine(database_connection_id: int | None) -> AsyncIterator[AsyncEngine]:
    if database_connection_id is None:
        yield executor_engine
        return

    row = await get_connection_row(database_connection_id)
    if row is None:
        raise ValueError(f"Database connection {database_connection_id} was not found.")

    engine = _engine_from_config(row)
    try:
        yield engine
    finally:
        await engine.dispose()


async def create_database_connection(
    request: DatabaseConnectionCreate,
) -> DatabaseConnectionResponse:
    async with metadata_engine.begin() as conn:
        row = (await conn.execute(
            text("""
                INSERT INTO dq_config.database_connections
                    (name, db_type, host, port, database_name, username, password_secret)
                VALUES
                    (:name, :db_type, :host, :port, :database, :username, :password)
                RETURNING *
            """),
            {
                "name": request.name,
                "db_type": request.db_type,
                "host": request.host,
                "port": request.port,
                "database": request.database,
                "username": request.username,
                "password": request.password,
            },
        )).mappings().one()
    return _database_response(row)


async def list_database_connections() -> list[DatabaseConnectionResponse]:
    async with metadata_engine.connect() as conn:
        rows = (await conn.execute(
            text("""
                SELECT *
                FROM dq_config.database_connections
                ORDER BY id
            """)
        )).mappings().all()
    return [_database_response(row) for row in rows]


async def get_connection_row(connection_id: int) -> dict[str, Any] | None:
    async with metadata_engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT * FROM dq_config.database_connections WHERE id = :id"),
            {"id": connection_id},
        )).mappings().first()
    return dict(row) if row else None


async def delete_database_connection(connection_id: int) -> bool:
    async with metadata_engine.begin() as conn:
        await conn.execute(
            text("""
                UPDATE dq_config.dq_rules
                SET database_connection_id = NULL
                WHERE database_connection_id = :id
            """),
            {"id": connection_id},
        )
        result = await conn.execute(
            text("DELETE FROM dq_config.database_connections WHERE id = :id RETURNING id"),
            {"id": connection_id},
        )
    return result.scalar_one_or_none() is not None


async def test_database_connection(connection_id: int) -> DatabaseTestResponse:
    row = await get_connection_row(connection_id)
    if row is None:
        raise ValueError("Database connection not found.")

    table_count = 0
    status = "connected"
    message = "Connection successful."
    try:
        engine = _engine_from_config(row)
        async with engine.connect() as conn:
            table_count = int((await conn.execute(text("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_type = 'BASE TABLE'
            """))).scalar_one())
    except Exception as exc:
        status = "failed"
        message = str(exc)
    finally:
        if "engine" in locals():
            await engine.dispose()

    async with metadata_engine.begin() as conn:
        await conn.execute(
            text("""
                UPDATE dq_config.database_connections
                SET status = :status, last_tested_at = :last_tested_at, updated_at = NOW()
                WHERE id = :id
            """),
            {"id": connection_id, "status": status, "last_tested_at": datetime.now(UTC)},
        )

    return DatabaseTestResponse(
        id=connection_id,
        status=status,
        message=message,
        table_count=table_count,
    )


async def get_database_schema(connection_id: int) -> DatabaseSchemaResponse:
    async with target_engine(connection_id) as engine:
        async with engine.connect() as conn:
            table_rows = (await conn.execute(text("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                  AND table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
            """))).mappings().all()

            column_rows = (await conn.execute(text("""
                SELECT table_schema, table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name, ordinal_position
            """))).mappings().all()

    columns_by_table: dict[tuple[str, str], list[ColumnInfo]] = {}
    for col in column_rows:
        key = (col["table_schema"], col["table_name"])
        columns_by_table.setdefault(key, []).append(
            ColumnInfo(
                name=col["column_name"],
                data_type=col["data_type"],
                nullable=col["is_nullable"] == "YES",
            )
        )

    tables = [
        TableInfo(
            schema_name=row["table_schema"],
            table_name=row["table_name"],
            qualified_name=f"{row['table_schema']}.{row['table_name']}",
            columns=columns_by_table.get((row["table_schema"], row["table_name"]), []),
        )
        for row in table_rows
    ]
    return DatabaseSchemaResponse(database_id=connection_id, tables=tables)


def _database_response(row: Any) -> DatabaseConnectionResponse:
    data = dict(row)
    return DatabaseConnectionResponse(
        id=data["id"],
        name=data["name"],
        db_type=data["db_type"],
        host=data["host"],
        port=data["port"],
        database=data["database_name"],
        username=data["username"],
        status=data["status"],
        last_tested_at=data["last_tested_at"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )
