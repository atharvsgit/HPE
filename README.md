# Data Quality Daemon

Dockerized FastAPI and PostgreSQL test harness for SQL-based data quality rules.

Current scope:

- Ad hoc SQL rule execution with `POST /rules/run`
- Persistent approved rule registry
- Manual execution of saved rules
- APScheduler-based execution of enabled saved rules with cron schedules
- Persisted execution results linked back to saved rules
- Platform Intelligence APIs for profiling, rule suggestions, anomaly detection, drift detection, and full Prefect pipeline orchestration
- Recurring full-pipeline schedules through a dedicated platform scheduler daemon

Still intentionally out of scope: natural-language parsing and UI.

## Run

Create a local `.env` from `.env.example` and set local database passwords:

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

The API starts at:

```text
http://localhost:8000
```

`docker compose up --build` starts four services:

- `postgres`: PostgreSQL test database
- `api`: FastAPI service
- `scheduler`: long-running APScheduler daemon for saved validation rules
- `platform_scheduler`: long-running APScheduler daemon for full Platform Intelligence pipeline schedules

PostgreSQL starts with:

- database: `dq_test`
- superuser: `postgres`
- execution role for submitted SQL: `dq_executor`
- metadata role for saved rules/results: `dq_app`
- schemas: `business_data`, `dq_config`, `dq_results`, `dq_platform`

If you already ran an older milestone with a persistent Docker volume, recreate the database once so the new registry schema is initialized:

```bash
docker compose down -v
docker compose up --build
```

## SQL Contract

Rule SQL must be one `SELECT` statement returning exactly one row and one numeric aggregate column named `violation_count` or `observed_value`.

The API rejects obvious mutation and DDL statements before saving or executing SQL. Actual rule execution uses the restricted `dq_executor` role inside a read-only transaction with a statement timeout.

## Ad Hoc Execution

Use this endpoint for one-off SQL rules that are not saved:

```http
POST /rules/run
```

```bash
curl -X POST http://localhost:8000/rules/run \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "No active employee has negative salary",
    "sql": "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE status = '\''active'\'' AND salary < 0;",
    "expected_result": {
      "type": "zero_violations"
    }
  }'
```

## Saved Rules

### Create Rule

```http
POST /rules
```

```bash
curl -X POST http://localhost:8000/rules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "No active employee has negative salary",
    "sql": "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE status = '\''active'\'' AND salary < 0;",
    "expected_result": {
      "type": "zero_violations"
    },
    "schedule_cron": null,
    "is_enabled": true
  }'
```

### List Rules

```bash
curl http://localhost:8000/rules
```

### Get One Rule

```bash
curl http://localhost:8000/rules/1
```

### Run Saved Rule Now

```bash
curl -X POST http://localhost:8000/rules/1/run
```

The result is persisted to `dq_results.test_results` with `rule_id = 1`.

### Get Recent Results For A Rule

```bash
curl http://localhost:8000/rules/1/results?limit=20
```

## Scheduled Rules

Saved rules are schedulable when:

- `is_enabled` is `true`
- `schedule_cron` is not null
- `schedule_cron` is a valid standard 5-field cron expression

Cron fields are interpreted as:

```text
minute hour day_of_month month day_of_week
```

Examples:

```text
*/5 * * * *
0 0 * * *
0 2 * * 1
0 3 1 * *
0 4 1 6 *
```

The scheduler loads rules at startup. For this milestone, changed or newly created schedules require restarting the scheduler container:

```bash
docker compose restart scheduler
```

### Create A Scheduled Rule

```bash
curl -X POST http://localhost:8000/rules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "Scheduled active employee salary check",
    "sql": "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE status = '\''active'\'' AND salary < 0;",
    "expected_result": {
      "type": "zero_violations"
    },
    "schedule_cron": "*/5 * * * *",
    "is_enabled": true
  }'
```

Invalid cron expressions are rejected at creation time with HTTP `400`.

### Scheduler Classifications

```bash
curl http://localhost:8000/scheduler/rules
```

Each rule is classified as one of:

- `schedulable`
- `disabled`
- `missing_schedule`
- `invalid_cron`

### Jitter

Scheduled jobs apply random execution jitter before running so many rules do not hit PostgreSQL at exactly the same second.

Default jitter is `120` seconds. Override it for local testing:

```bash
RULE_EXECUTION_JITTER_SECONDS=0 docker compose up --build
```

## Platform Intelligence & Workflow System

Manjunath's Platform Intelligence layer is exposed under `/platform` and integrates with Atharv's rule registry/executor.

Pipeline flow:

```text
profile → validate saved rules → suggest/sanitize rules → detect anomalies → store metadata/events
```

Core endpoints:

```text
POST /platform/pipeline/trigger
GET  /platform/pipeline/runs
GET  /platform/pipeline/runs/{run_id}
GET  /platform/pipeline/runs/{run_id}/events
POST /platform/pipeline/schedules
GET  /platform/pipeline/schedules
PATCH /platform/pipeline/schedules/{schedule_id}
POST /platform/profile
GET  /platform/profile/{table_name}
POST /platform/suggestions
GET  /platform/suggestions
POST /platform/suggestions/{suggestion_id}/apply
POST /platform/anomaly/detect
GET  /platform/anomaly/results
POST /platform/drift/detect
GET  /platform/drift/results
```

The platform layer includes:

- Prefect flow controller with retry policies and dependency graph resolution
- Persistent execution logging in `dq_platform.pipeline_events`
- Pipeline schedules in `dq_platform.pipeline_schedules`
- Polars profiling for schema, nulls, distributions, uniqueness, and statistics
- Rule suggestions through offline heuristics or Gemini, followed by mandatory sanitization
- SQLGlot query planning plus Atharv's SQL safety validator before suggested rules are stored
- Saved-rule validation by calling Atharv's existing executor for rules targeting the table
- Anomaly detection with Isolation Forest, Z-score, and Local Outlier Factor
- Evidently-based drift detection endpoints

Create a recurring full-pipeline schedule:

```bash
curl -X POST http://localhost:8000/platform/pipeline/schedules \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "business_data.employees",
    "schedule_cron": "0 * * * *",
    "is_enabled": true,
    "description": "Hourly employee data quality pipeline"
  }'
```

Schedule changes are loaded when the `platform_scheduler` container starts. Restart it after adding or changing schedules:

```bash
docker compose restart platform_scheduler
```

## Expected Result Types

### `zero_violations`

Passes when the aggregate result is `0`.

```json
{
  "type": "zero_violations"
}
```

### `min_threshold`

Passes when the aggregate result is greater than or equal to `value`.

```json
{
  "type": "min_threshold",
  "value": 1000
}
```

### `max_threshold`

Passes when the aggregate result is less than or equal to `value`.

```json
{
  "type": "max_threshold",
  "value": 25
}
```

### `equals`

Passes when the aggregate result exactly equals `value`.

```json
{
  "type": "equals",
  "value": 25000
}
```

## Inspect PostgreSQL

Open `psql`:

```bash
docker compose exec postgres psql -U postgres -d dq_test
```

Saved rules:

```sql
SELECT
    rule_id,
    rule_name,
    expected_result_type,
    expected_result_value,
    is_enabled,
    schedule_cron,
    created_at,
    updated_at
FROM dq_config.dq_rules
ORDER BY rule_id;
```

Execution results:

```sql
SELECT
    result_id,
    rule_id,
    rule_name,
    status,
    observed_key,
    observed_value,
    execution_time_ms,
    error_message,
    executed_at
FROM dq_results.test_results
ORDER BY result_id DESC
LIMIT 20;
```

Results created by the scheduler have the saved rule's `rule_id`.

## Database Relationships

The database has four schemas:

- `business_data`: sample company database tables checked by validation SQL
- `dq_config`: saved rule metadata
- `dq_results`: persisted execution results
- `dq_platform`: pipeline runs, schedules, events, profiles, suggestions, anomalies, and drift results

```mermaid
erDiagram
    EMPLOYEES {
        BIGSERIAL employee_id PK
        TEXT full_name
        TEXT status
        NUMERIC salary
        TEXT department
        DATE hired_at
    }

    STUDENTS {
        BIGSERIAL student_id PK
        TEXT full_name
        DATE enrollment_date
        TEXT admission_status
        TEXT grade_level
    }

    DQ_RULES {
        BIGSERIAL rule_id PK
        TEXT rule_name
        TEXT sql_text
        TEXT expected_result_type
        NUMERIC expected_result_value
        BOOLEAN is_enabled
        TEXT schedule_cron
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    TEST_RESULTS {
        BIGSERIAL result_id PK
        BIGINT rule_id FK
        TEXT rule_name
        TEXT sql_text
        TEXT status
        TEXT observed_key
        NUMERIC observed_value
        INTEGER execution_time_ms
        TEXT error_message
        TIMESTAMPTZ executed_at
    }

    DQ_RULES ||--o{ TEST_RESULTS : "one saved rule has zero or many execution results"
    DQ_RULES }o--o{ EMPLOYEES : "conceptually queries aggregate rows from"
    DQ_RULES }o--o{ STUDENTS : "conceptually queries aggregate rows from"
```

Cardinality:

- `DQ_RULES ||--o{ TEST_RESULTS`: one saved rule can have zero, one, or many execution result rows.
- `TEST_RESULTS.rule_id` is nullable, so ad hoc `/rules/run` executions can exist without a saved rule.
- `DQ_RULES }o--o{ EMPLOYEES`: conceptual many-to-many read relationship. Many rules may query employee data, and each rule may aggregate over many employee rows.
- `DQ_RULES }o--o{ STUDENTS`: conceptual many-to-many read relationship. Many rules may query student data, and each rule may aggregate over many student rows.

Only `dq_results.test_results.rule_id -> dq_config.dq_rules.rule_id` is enforced as a real foreign key. The relationships to `business_data` tables are conceptual because rules reference those tables through `sql_text`.

## Failure Notifications

The daemon can send email notifications when a rule execution ends with `FAIL` or `ERROR`.
Passing rules are not notified.
For count-based failure rules where the executor can derive a row preview, the alert includes a small sample of violating rows in addition to the aggregate result.

Email settings are optional. Leave `SMTP_SERVER` blank to disable notifications:

```bash
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=5
NOTIFICATION_EMAIL_FROM=alerts@dataqualitydaemon.local
ADMIN_EMAIL=manjunathpatil3155@gmail.com
```

The API and scheduler containers both receive these settings from Docker Compose.

## Tests

Run the test suite in Docker:

```bash
docker compose run --rm --no-deps api pytest
```

The tests cover evaluator behavior, SQL safety validation, cron parsing, scheduler classification, scheduled execution dispatch, ad hoc execution behavior, saved-rule endpoint behavior, manual saved-rule execution, saved-rule result retrieval, failure notification behavior, ingestion utilities, LLM draft workflows, Platform Intelligence routing, profiling utilities, query planning, rule sanitization, anomaly detection helpers, and orchestration dependency resolution.

## Frontend Application

The merged frontend is a React and TailwindCSS single-page application for the database-backed data quality workflow.

Frontend features:

- PostgreSQL database connection form
- Table schema display and local connection state management
- Dynamic rule builder UI
- Validation history page
- Dashboard for saved rules, scheduler classifications, and persisted aggregate execution results

Frontend tech stack:

- React
- Vite
- TailwindCSS
- Axios

Run the frontend locally:

```bash
npm install
npm run dev
```

Frontend scripts:

- `npm run dev`: start the local development server
- `npm run build`: create a production build
- `npm run preview`: preview the production build locally

Frontend folder structure:

- `src/components/ingestion`: PostgreSQL database form and schema table
- `src/components/ruleBuilder`: rule authoring and validation results UI
- `src/components/common`: shared UI utilities such as loaders, toasts, modals, and badges
- `src/pages`: route-level pages for ingestion, rules, validation history, and dashboard
- `src/services`: Axios client, endpoint wrappers, and rules API wrappers
- `src/context`: shared database connection state across connection, rule building, and dashboard views
- `src/assets`: visual assets for the application shell
