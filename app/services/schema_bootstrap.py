from __future__ import annotations

import os

from sqlalchemy.engine import URL
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.db.session import metadata_engine


def _bootstrap_engine() -> AsyncEngine:
    password = os.getenv("POSTGRES_PASSWORD")
    user = os.getenv("POSTGRES_USER", "postgres")
    database = os.getenv("POSTGRES_DB", "dq_test")
    host = os.getenv("POSTGRES_HOST")
    if not password or not host:
        return metadata_engine

    return create_async_engine(
        URL.create(
            "postgresql+asyncpg",
            username=user,
            password=password,
            host=host,
            port=5432,
            database=database,
        ),
        pool_pre_ping=True,
    )


async def ensure_product_schema() -> None:
    """Create revamp metadata objects for existing Docker volumes."""
    bootstrap_engine = _bootstrap_engine()
    async with bootstrap_engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_config.database_connections (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                db_type TEXT NOT NULL DEFAULT 'postgresql',
                host TEXT NOT NULL,
                port INTEGER NOT NULL DEFAULT 5432,
                database_name TEXT NOT NULL,
                username TEXT NOT NULL,
                password_secret TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'untested',
                last_tested_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            ALTER TABLE dq_config.dq_rules
            ADD COLUMN IF NOT EXISTS database_connection_id BIGINT NULL REFERENCES dq_config.database_connections(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS table_name TEXT NULL,
            ADD COLUMN IF NOT EXISTS schedule_text TEXT NULL,
            ADD COLUMN IF NOT EXISTS notification_channels JSONB NOT NULL DEFAULT '["slack"]'::jsonb,
            ADD COLUMN IF NOT EXISTS source_prompt TEXT NULL
        """))
        await conn.execute(text("""
            ALTER TABLE dq_results.test_results
            ADD COLUMN IF NOT EXISTS database_connection_id BIGINT NULL REFERENCES dq_config.database_connections(id) ON DELETE SET NULL
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.notification_deliveries (
                id BIGSERIAL PRIMARY KEY,
                rule_id BIGINT NULL REFERENCES dq_config.dq_rules(rule_id) ON DELETE SET NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_config.app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT,
                is_secret BOOLEAN NOT NULL DEFAULT false,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            GRANT USAGE, CREATE ON SCHEMA dq_config TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE ON SCHEMA dq_results TO dq_app
        """))
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE, DELETE ON dq_config.database_connections TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE, SELECT ON SEQUENCE dq_config.database_connections_id_seq TO dq_app
        """))
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE, DELETE ON dq_config.app_settings TO dq_app
        """))
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.notification_deliveries TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE, SELECT ON SEQUENCE dq_results.notification_deliveries_id_seq TO dq_app
        """))
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE ON dq_results.test_results TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE, SELECT ON SEQUENCE dq_results.test_results_result_id_seq TO dq_app
        """))

    if bootstrap_engine is not metadata_engine:
        await bootstrap_engine.dispose()

    await ensure_default_database_connection()


async def ensure_default_database_connection() -> None:
    """Seed the Docker demo database as the first connection when none exists."""
    host = os.getenv("POSTGRES_HOST", "postgres")
    database = os.getenv("POSTGRES_DB", "dq_test")
    password = os.getenv("DQ_EXECUTOR_PASSWORD", "dq_executor_password")

    async with metadata_engine.begin() as conn:
        count = (await conn.execute(text("SELECT COUNT(*) FROM dq_config.database_connections"))).scalar_one()
        if count:
            return

        await conn.execute(
            text("""
                INSERT INTO dq_config.database_connections
                    (name, db_type, host, port, database_name, username, password_secret, status)
                VALUES
                    (:name, 'postgresql', :host, 5432, :database, 'dq_executor', :password, 'untested')
            """),
            {
                "name": "Docker Demo Postgres",
                "host": host,
                "database": database,
                "password": password,
            },
        )
