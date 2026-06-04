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
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS dq_config"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS dq_results"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS dq_platform"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_config.dq_rules (
                rule_id BIGSERIAL PRIMARY KEY,
                rule_name TEXT NOT NULL,
                sql_text TEXT NOT NULL,
                expected_result_type TEXT NOT NULL,
                expected_result_value NUMERIC NULL,
                is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                schedule_cron TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT dq_rules_expected_result_type_check CHECK (
                    expected_result_type IN (
                        'zero_violations',
                        'min_threshold',
                        'max_threshold',
                        'equals'
                    )
                ),
                CONSTRAINT dq_rules_expected_result_value_check CHECK (
                    expected_result_type = 'zero_violations'
                    OR expected_result_value IS NOT NULL
                )
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.test_results (
                result_id BIGSERIAL PRIMARY KEY,
                rule_id BIGINT NULL REFERENCES dq_config.dq_rules(rule_id),
                rule_name TEXT NOT NULL,
                sql_text TEXT NOT NULL,
                status TEXT NOT NULL,
                observed_key TEXT,
                observed_value NUMERIC,
                execution_time_ms INTEGER,
                error_message TEXT,
                executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_test_results_rule_id_executed_at
            ON dq_results.test_results (rule_id, executed_at DESC)
        """))
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
            ALTER TABLE dq_config.dq_rules
            ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'medium',
            ADD COLUMN IF NOT EXISTS quality_score NUMERIC(5,2) DEFAULT 100.00,
            ADD COLUMN IF NOT EXISTS is_noisy BOOLEAN DEFAULT false,
            ADD COLUMN IF NOT EXISTS false_positive_rate NUMERIC(5,2) DEFAULT 0.00
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_config.notification_policies (
                id BIGSERIAL PRIMARY KEY,
                rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
                immediate_threshold NUMERIC,
                batch_window_minutes INTEGER DEFAULT 60,
                deduplication_window_minutes INTEGER DEFAULT 15,
                enable_llm_summary BOOLEAN DEFAULT false,
                enable_fix_suggestions BOOLEAN DEFAULT false,
                slack_enabled BOOLEAN DEFAULT true,
                email_enabled BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.violation_events (
                id BIGSERIAL PRIMARY KEY,
                rule_result_id BIGINT REFERENCES dq_results.test_results(result_id) ON DELETE CASCADE,
                rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
                severity TEXT,
                violation_count NUMERIC,
                sample_rows JSONB,
                fingerprint TEXT,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.violation_batches (
                id BIGSERIAL PRIMARY KEY,
                rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
                severity TEXT,
                first_seen TIMESTAMPTZ,
                last_seen TIMESTAMPTZ,
                total_occurrences INTEGER DEFAULT 1,
                total_violation_count NUMERIC,
                status TEXT DEFAULT 'open'
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.llm_summaries (
                id SERIAL PRIMARY KEY,
                violation_batch_id INTEGER NOT NULL REFERENCES dq_results.violation_batches(id) ON DELETE CASCADE,
                summary TEXT NOT NULL,
                root_causes JSONB DEFAULT '[]'::JSONB,
                suggested_fixes JSONB DEFAULT '[]'::JSONB,
                business_impact TEXT,
                raw_response TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            ALTER TABLE dq_results.llm_summaries DROP CONSTRAINT IF EXISTS uq_violation_batch_id
        """))
        await conn.execute(text("""
            ALTER TABLE dq_results.llm_summaries
            ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(50) DEFAULT 'v1.0.0',
            ADD COLUMN IF NOT EXISTS effective_confidence VARCHAR(15),
            ADD COLUMN IF NOT EXISTS provider_name VARCHAR(50),
            ADD COLUMN IF NOT EXISTS model_name VARCHAR(100),
            ADD COLUMN IF NOT EXISTS token_usage INTEGER,
            ADD COLUMN IF NOT EXISTS parsing_failure BOOLEAN DEFAULT FALSE
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_llm_summaries_batch_created
            ON dq_results.llm_summaries(violation_batch_id, created_at DESC)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.llm_feedback (
                id SERIAL PRIMARY KEY,
                violation_batch_id INTEGER REFERENCES dq_results.violation_batches(id) ON DELETE CASCADE,
                llm_summary_id INTEGER REFERENCES dq_results.llm_summaries(id) ON DELETE CASCADE,
                feedback_type VARCHAR(20) NOT NULL,
                edited_summary TEXT,
                edited_fixes TEXT,
                feedback_notes TEXT,
                user_id VARCHAR(100) DEFAULT 'system',
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_llm_feedback_batch
            ON dq_results.llm_feedback(violation_batch_id, created_at DESC)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.ai_rule_generations (
                id SERIAL PRIMARY KEY,
                prompt TEXT NOT NULL,
                generated_sql TEXT,
                explanation TEXT,
                assumptions JSONB,
                possible_edge_cases JSONB,
                confidence VARCHAR(10),
                provider_name VARCHAR(50),
                model_name VARCHAR(100),
                prompt_version VARCHAR(50),
                parsing_failure BOOLEAN DEFAULT FALSE,
                approved BOOLEAN DEFAULT FALSE,
                approved_by VARCHAR(100),
                edited_after_generation BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                original_prompt TEXT,
                reviewed_sql TEXT,
                approval_timestamp TIMESTAMPTZ
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.rule_improvement_suggestions (
                id SERIAL PRIMARY KEY,
                rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
                suggestion_type VARCHAR(50) NOT NULL,
                suggested_sql TEXT,
                reasoning TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_results.incident_embeddings (
                id SERIAL PRIMARY KEY,
                violation_batch_id BIGINT REFERENCES dq_results.violation_batches(id) ON DELETE CASCADE,
                rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
                incident_text TEXT NOT NULL,
                embedding JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE SCHEMA IF NOT EXISTS dq_platform
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_platform.pipeline_runs (
                run_id BIGSERIAL PRIMARY KEY,
                table_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED')),
                triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                finished_at TIMESTAMPTZ,
                error TEXT,
                metadata JSONB
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_platform.dataset_profiles (
                profile_id BIGSERIAL PRIMARY KEY,
                run_id BIGINT REFERENCES dq_platform.pipeline_runs(run_id) ON DELETE SET NULL,
                table_name TEXT NOT NULL,
                row_count BIGINT,
                column_count INTEGER,
                null_summary JSONB,
                schema_info JSONB,
                statistics JSONB,
                uniqueness JSONB,
                profiled_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_profiles_table ON dq_platform.dataset_profiles(table_name)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_profiles_run ON dq_platform.dataset_profiles(run_id)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_platform.rule_suggestions (
                suggestion_id BIGSERIAL PRIMARY KEY,
                profile_id BIGINT REFERENCES dq_platform.dataset_profiles(profile_id) ON DELETE SET NULL,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                suggestion_type TEXT NOT NULL CHECK (suggestion_type IN ('heuristic', 'gemini')),
                suggested_rule_name TEXT NOT NULL,
                suggested_sql TEXT NOT NULL,
                expected_result_type TEXT NOT NULL,
                expected_result_value NUMERIC,
                confidence NUMERIC CHECK (confidence >= 0 AND confidence <= 1),
                applied BOOLEAN NOT NULL DEFAULT FALSE,
                applied_rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_suggestions_table ON dq_platform.rule_suggestions(table_name)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_suggestions_applied ON dq_platform.rule_suggestions(applied)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_platform.anomaly_results (
                anomaly_id BIGSERIAL PRIMARY KEY,
                run_id BIGINT REFERENCES dq_platform.pipeline_runs(run_id) ON DELETE SET NULL,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                method TEXT NOT NULL CHECK (method IN ('isolation_forest', 'zscore', 'lof')),
                anomaly_count INTEGER NOT NULL,
                total_rows INTEGER NOT NULL,
                anomaly_pct NUMERIC(6, 3) NOT NULL,
                details JSONB,
                detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_anomalies_table ON dq_platform.anomaly_results(table_name)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dq_platform.drift_results (
                drift_id BIGSERIAL PRIMARY KEY,
                run_id BIGINT REFERENCES dq_platform.pipeline_runs(run_id) ON DELETE SET NULL,
                reference_table TEXT NOT NULL,
                current_table TEXT NOT NULL,
                column_name TEXT NOT NULL,
                stat_test TEXT NOT NULL,
                drift_score NUMERIC(10, 6) NOT NULL,
                is_drifted BOOLEAN NOT NULL,
                detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_drift_tables
            ON dq_platform.drift_results(reference_table, current_table)
        """))
        await conn.execute(text("""
            GRANT USAGE, CREATE ON SCHEMA dq_config TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE ON SCHEMA dq_results TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE ON SCHEMA dq_platform TO dq_app
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
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA dq_config TO dq_app
        """))
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA dq_results TO dq_app
        """))
        await conn.execute(text("""
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA dq_platform TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dq_config TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dq_results TO dq_app
        """))
        await conn.execute(text("""
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dq_platform TO dq_app
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
