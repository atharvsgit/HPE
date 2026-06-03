-- Product revamp schema: persisted database connections, orchestrator job metadata,
-- and notification delivery logs.

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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT database_connections_db_type_check CHECK (db_type IN ('postgresql')),
    CONSTRAINT database_connections_status_check CHECK (status IN ('untested', 'connected', 'failed'))
);

ALTER TABLE dq_config.dq_rules
ADD COLUMN IF NOT EXISTS database_connection_id BIGINT NULL REFERENCES dq_config.database_connections(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS table_name TEXT NULL,
ADD COLUMN IF NOT EXISTS schedule_text TEXT NULL,
ADD COLUMN IF NOT EXISTS notification_channels JSONB NOT NULL DEFAULT '["slack"]'::jsonb,
ADD COLUMN IF NOT EXISTS source_prompt TEXT NULL;

ALTER TABLE dq_results.test_results
ADD COLUMN IF NOT EXISTS database_connection_id BIGINT NULL REFERENCES dq_config.database_connections(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS dq_results.notification_deliveries (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT NULL REFERENCES dq_config.dq_rules(rule_id) ON DELETE SET NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT notification_deliveries_channel_check CHECK (channel IN ('slack', 'email')),
    CONSTRAINT notification_deliveries_status_check CHECK (status IN ('sent', 'failed', 'skipped'))
);

CREATE TABLE IF NOT EXISTS dq_config.app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT,
    is_secret BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

GRANT USAGE, CREATE ON SCHEMA dq_config TO dq_app;
GRANT USAGE ON SCHEMA dq_results TO dq_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_config.database_connections TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_config.database_connections_id_seq TO dq_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_config.app_settings TO dq_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.notification_deliveries TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.notification_deliveries_id_seq TO dq_app;

GRANT SELECT, UPDATE ON dq_config.dq_rules TO dq_app;
GRANT SELECT, INSERT, UPDATE ON dq_results.test_results TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.test_results_result_id_seq TO dq_app;
