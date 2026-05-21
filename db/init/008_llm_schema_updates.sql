-- 008_llm_schema_updates.sql

-- Drop the unique constraint to allow multiple re-enrichment versions
ALTER TABLE dq_results.llm_summaries DROP CONSTRAINT IF EXISTS uq_violation_batch_id;

-- Add new observability and audit columns
ALTER TABLE dq_results.llm_summaries ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(50) DEFAULT 'v1.0.0';
ALTER TABLE dq_results.llm_summaries ADD COLUMN IF NOT EXISTS effective_confidence VARCHAR(15);
ALTER TABLE dq_results.llm_summaries ADD COLUMN IF NOT EXISTS provider_name VARCHAR(50);
ALTER TABLE dq_results.llm_summaries ADD COLUMN IF NOT EXISTS model_name VARCHAR(100);
ALTER TABLE dq_results.llm_summaries ADD COLUMN IF NOT EXISTS token_usage INTEGER;
ALTER TABLE dq_results.llm_summaries ADD COLUMN IF NOT EXISTS parsing_failure BOOLEAN DEFAULT FALSE;

-- To help query the latest enrichment per batch efficiently
CREATE INDEX IF NOT EXISTS idx_llm_summaries_batch_created 
ON dq_results.llm_summaries(violation_batch_id, created_at DESC);
