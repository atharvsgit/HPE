CREATE TABLE IF NOT EXISTS business_data.employees (
    employee_id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    status TEXT NOT NULL,
    salary NUMERIC(12, 2),
    department TEXT,
    hired_at DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS business_data.students (
    student_id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    enrollment_date DATE NOT NULL,
    admission_status TEXT NOT NULL,
    grade_level TEXT
);

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
);

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
);

ALTER TABLE dq_results.test_results
ADD COLUMN IF NOT EXISTS rule_id BIGINT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'test_results_rule_id_fkey'
    ) THEN
        ALTER TABLE dq_results.test_results
        ADD CONSTRAINT test_results_rule_id_fkey
        FOREIGN KEY (rule_id)
        REFERENCES dq_config.dq_rules(rule_id);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_test_results_rule_id_executed_at
ON dq_results.test_results (rule_id, executed_at DESC);
