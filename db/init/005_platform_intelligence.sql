-- =============================================================================
-- 005_platform_intelligence.sql
-- Platform Intelligence schema: pipeline runs, profiling, rule suggestions,
-- anomaly detection, and data drift tracking.
-- Author: Manjunath Patil (Platform Intelligence & Workflow System)
-- =============================================================================

-- Create dedicated schema
CREATE SCHEMA IF NOT EXISTS dq_platform;

-- ---------------------------------------------------------------------------
-- pipeline_runs: tracks each full Prefect pipeline execution
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_platform.pipeline_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    table_name    TEXT NOT NULL,
    status        TEXT NOT NULL
                      CHECK (status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED')),
    triggered_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at   TIMESTAMPTZ,
    error         TEXT,
    metadata      JSONB          -- stage timings, task counts, configuration
);

-- ---------------------------------------------------------------------------
-- dataset_profiles: profiling results produced by the Polars-based engine
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_platform.dataset_profiles (
    profile_id    BIGSERIAL PRIMARY KEY,
    run_id        BIGINT REFERENCES dq_platform.pipeline_runs(run_id) ON DELETE SET NULL,
    table_name    TEXT NOT NULL,
    row_count     BIGINT,
    column_count  INTEGER,
    null_summary  JSONB,    -- { "col": null_percentage, ... }
    schema_info   JSONB,    -- { "col": "dtype_string", ... }
    statistics    JSONB,    -- { "col": { min, max, mean, std, ... }, ... }
    uniqueness    JSONB,    -- { "col": unique_percentage, ... }
    profiled_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_profiles_table ON dq_platform.dataset_profiles(table_name);
CREATE INDEX idx_profiles_run   ON dq_platform.dataset_profiles(run_id);

-- ---------------------------------------------------------------------------
-- rule_suggestions: heuristic or LLM-generated rule candidates
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_platform.rule_suggestions (
    suggestion_id         BIGSERIAL PRIMARY KEY,
    profile_id            BIGINT REFERENCES dq_platform.dataset_profiles(profile_id) ON DELETE SET NULL,
    table_name            TEXT NOT NULL,
    column_name           TEXT NOT NULL,
    suggestion_type       TEXT NOT NULL CHECK (suggestion_type IN ('heuristic', 'gemini')),
    suggested_rule_name   TEXT NOT NULL,
    suggested_sql         TEXT NOT NULL,
    expected_result_type  TEXT NOT NULL,
    expected_result_value NUMERIC,
    confidence            NUMERIC CHECK (confidence >= 0 AND confidence <= 1),
    applied               BOOLEAN NOT NULL DEFAULT FALSE,
    applied_rule_id       BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_suggestions_table ON dq_platform.rule_suggestions(table_name);
CREATE INDEX idx_suggestions_applied ON dq_platform.rule_suggestions(applied);

-- ---------------------------------------------------------------------------
-- anomaly_results: per-column anomaly detection outputs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_platform.anomaly_results (
    anomaly_id    BIGSERIAL PRIMARY KEY,
    run_id        BIGINT REFERENCES dq_platform.pipeline_runs(run_id) ON DELETE SET NULL,
    table_name    TEXT NOT NULL,
    column_name   TEXT NOT NULL,
    method        TEXT NOT NULL CHECK (method IN ('isolation_forest', 'zscore', 'lof')),
    anomaly_count INTEGER NOT NULL,
    total_rows    INTEGER NOT NULL,
    anomaly_pct   NUMERIC(6, 3) NOT NULL,
    details       JSONB,    -- sample anomalous values / indices
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_anomalies_table ON dq_platform.anomaly_results(table_name);

-- ---------------------------------------------------------------------------
-- drift_results: per-column Evidently drift outputs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_platform.drift_results (
    drift_id          BIGSERIAL PRIMARY KEY,
    run_id            BIGINT REFERENCES dq_platform.pipeline_runs(run_id) ON DELETE SET NULL,
    reference_table   TEXT NOT NULL,
    current_table     TEXT NOT NULL,
    column_name       TEXT NOT NULL,
    stat_test         TEXT NOT NULL,
    drift_score       NUMERIC(10, 6) NOT NULL,
    is_drifted        BOOLEAN NOT NULL,
    detected_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_drift_tables ON dq_platform.drift_results(reference_table, current_table);

-- ---------------------------------------------------------------------------
-- Grant dq_app full access to the new schema
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA dq_platform TO dq_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA dq_platform TO dq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq_platform
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dq_app;
GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA dq_platform TO dq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq_platform
    GRANT USAGE, SELECT ON SEQUENCES TO dq_app;
