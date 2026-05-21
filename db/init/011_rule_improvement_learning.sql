-- 011_rule_improvement_learning.sql

-- 1. Add quality metrics to dq_rules
ALTER TABLE dq_config.dq_rules
ADD COLUMN IF NOT EXISTS quality_score NUMERIC(5,2) DEFAULT 100.00,
ADD COLUMN IF NOT EXISTS is_noisy BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS false_positive_rate NUMERIC(5,2) DEFAULT 0.00;

-- 2. Create rule_improvement_suggestions table
CREATE TABLE IF NOT EXISTS dq_results.rule_improvement_suggestions (
    id SERIAL PRIMARY KEY,
    rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
    suggestion_type VARCHAR(50) NOT NULL, -- 'threshold_tuning', 'null_handling', 'filter_refinement', etc.
    suggested_sql TEXT,
    reasoning TEXT,
    status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'reviewed', 'accepted', 'rejected', 'superseded'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Create incident_embeddings table (Abstract JSONB for now to preserve pgvector flexibility)
CREATE TABLE IF NOT EXISTS dq_results.incident_embeddings (
    id SERIAL PRIMARY KEY,
    violation_batch_id BIGINT REFERENCES dq_results.violation_batches(id) ON DELETE CASCADE,
    rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE CASCADE,
    incident_text TEXT NOT NULL,
    embedding JSONB, -- Designed to be easily cast or migrated to vector/pgvector later
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.rule_improvement_suggestions TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.rule_improvement_suggestions_id_seq TO dq_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.incident_embeddings TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.incident_embeddings_id_seq TO dq_app;
