-- 007_llm_summaries.sql
-- Creates the table for storing intelligent LLM summaries for violation batches.

CREATE TABLE IF NOT EXISTS dq_results.llm_summaries (
    id SERIAL PRIMARY KEY,
    violation_batch_id INTEGER NOT NULL REFERENCES dq_results.violation_batches(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    root_causes JSONB DEFAULT '[]'::JSONB,
    suggested_fixes JSONB DEFAULT '[]'::JSONB,
    business_impact TEXT,
    raw_response TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure idempotency: one summary per batch
    CONSTRAINT uq_violation_batch_id UNIQUE(violation_batch_id)
);

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.llm_summaries TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.llm_summaries_id_seq TO dq_app;
-- without complicated commands. The string literal 'enriched' will be valid if the column 
-- is a standard VARCHAR, but if it is an ENUM, we must alter it. 
-- Let's check how status is defined in 006_intelligent_alerts.sql.
-- If it's a VARCHAR, we are fine. If it's an ENUM, we add 'enriched'.
