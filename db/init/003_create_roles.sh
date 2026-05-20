#!/bin/sh
set -eu

: "${DQ_EXECUTOR_PASSWORD:?DQ_EXECUTOR_PASSWORD must be set}"
: "${DQ_APP_PASSWORD:?DQ_APP_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 \
  -v dq_executor_password="$DQ_EXECUTOR_PASSWORD" \
  -v dq_app_password="$DQ_APP_PASSWORD" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_executor') THEN
        CREATE ROLE dq_executor LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dq_app') THEN
        CREATE ROLE dq_app LOGIN;
    END IF;
END
$$;

ALTER ROLE dq_executor WITH LOGIN PASSWORD :'dq_executor_password';
ALTER ROLE dq_app WITH LOGIN PASSWORD :'dq_app_password';

GRANT USAGE ON SCHEMA business_data TO dq_executor;
GRANT SELECT ON ALL TABLES IN SCHEMA business_data TO dq_executor;

GRANT USAGE ON SCHEMA business_data TO dq_app;
GRANT SELECT ON ALL TABLES IN SCHEMA business_data TO dq_app;

GRANT USAGE ON SCHEMA dq_results TO dq_executor;
GRANT INSERT ON dq_results.test_results TO dq_executor;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dq_results TO dq_executor;

GRANT USAGE ON SCHEMA dq_config TO dq_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON dq_config.dq_rules TO dq_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dq_config TO dq_app;

GRANT USAGE ON SCHEMA dq_results TO dq_app;
GRANT SELECT, UPDATE(rule_id) ON dq_results.test_results TO dq_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA business_data GRANT SELECT ON TABLES TO dq_executor;
ALTER DEFAULT PRIVILEGES IN SCHEMA business_data GRANT SELECT ON TABLES TO dq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq_results GRANT INSERT ON TABLES TO dq_executor;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq_results GRANT USAGE, SELECT ON SEQUENCES TO dq_executor;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq_config GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq_config GRANT USAGE, SELECT ON SEQUENCES TO dq_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA dq_results GRANT SELECT ON TABLES TO dq_app;
SQL
