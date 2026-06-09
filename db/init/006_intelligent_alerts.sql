-- Add severity support to existing rules
ALTER TABLE dq_config.dq_rules 
ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'medium';

-- Table for rule-level notification and aggregation policies
CREATE TABLE IF NOT EXISTS dq_config.notification_policies (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
    immediate_threshold NUMERIC,
    batch_window_minutes INTEGER DEFAULT 60,
    deduplication_window_minutes INTEGER DEFAULT 5,
    enable_llm_summary BOOLEAN DEFAULT false,
    enable_fix_suggestions BOOLEAN DEFAULT false,
    slack_enabled BOOLEAN DEFAULT true,
    email_enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Table for individual raw violation events
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
);

-- Table for aggregated batches of violations
CREATE TABLE IF NOT EXISTS dq_results.violation_batches (
    id BIGSERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
    severity TEXT,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    total_occurrences INTEGER DEFAULT 1,
    total_violation_count NUMERIC,
    status TEXT DEFAULT 'open'
);

-- Grant permissions to dq_app role
GRANT SELECT, INSERT, UPDATE, DELETE ON dq_config.notification_policies TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_config.notification_policies_id_seq TO dq_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.violation_events TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.violation_events_id_seq TO dq_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.violation_batches TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.violation_batches_id_seq TO dq_app;
