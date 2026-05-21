-- 009_llm_feedback.sql

CREATE TABLE IF NOT EXISTS dq_results.llm_feedback (
    id SERIAL PRIMARY KEY,
    violation_batch_id INTEGER REFERENCES dq_results.violation_batches(id) ON DELETE CASCADE,
    llm_summary_id INTEGER REFERENCES dq_results.llm_summaries(id) ON DELETE CASCADE,
    feedback_type VARCHAR(20) NOT NULL, -- 'accept', 'reject', 'edit', 'annotate'
    edited_summary TEXT,
    edited_fixes TEXT,
    feedback_notes TEXT,
    user_id VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_llm_feedback_batch ON dq_results.llm_feedback(violation_batch_id, created_at DESC);

GRANT SELECT, INSERT, UPDATE, DELETE ON dq_results.llm_feedback TO dq_app;
GRANT USAGE, SELECT ON SEQUENCE dq_results.llm_feedback_id_seq TO dq_app;
