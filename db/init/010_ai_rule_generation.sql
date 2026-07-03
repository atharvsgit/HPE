-- 010_ai_rule_generation.sql

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
    
    -- Additional governance tracking from requirements
    original_prompt TEXT, -- To track original vs sanitized/enriched prompt if needed, though 'prompt' might suffice. Let's stick to prompt, but add original_prompt per requirement 8.
    reviewed_sql TEXT,
    approval_timestamp TIMESTAMPTZ,
    saved_rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE SET NULL
);

ALTER TABLE dq_results.ai_rule_generations
ADD COLUMN IF NOT EXISTS saved_rule_id BIGINT REFERENCES dq_config.dq_rules(rule_id) ON DELETE SET NULL;

-- Ensure dq_executor does NOT have write access to this table.
-- dq_api can read/write to this table.
GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.ai_rule_generations TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.ai_rule_generations_id_seq TO dq_app;
