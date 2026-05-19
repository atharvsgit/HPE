# Data Quality Daemon — Architecture & Build Specification

## 1. Objective

This document defines the initial implementation scope for the **Data Quality Daemon**.

The broader platform will eventually accept natural-language business rules, use an LLM to generate SQL, validate the SQL with AST guardrails, store approved rules, execute them on a schedule, and generate reports.

For the current milestone, the focus is narrower:

- Build the **daemon/execution layer**.
- Build a simple **test API** that accepts already-written SQL.
- Build a **PostgreSQL test database** with bulk-inserted sample data.
- Run the system in a **Linux-compatible Docker environment**.
- Return validation results in **JSON format**.

Natural-language parsing, LLM interpretation, human approval, and final reporting will be handled by other teammates later.

---

## 2. Current Scope

### In Scope

The first version should support:

1. A FastAPI service that accepts validation SQL from the user.
2. A daemon that receives or reads the SQL rule and executes it safely.
3. PostgreSQL as the database engine.
4. Bulk sample data for testing.
5. JSON output containing whether the rule passed or failed.
6. Docker-based local development and Linux runtime compatibility.
7. Basic safety controls:
   - Read-only execution.
   - Statement timeout.
   - Restricted SQL shape.
   - Connection pooling.
   - Error handling.

### Out of Scope for This Milestone

The following are intentionally excluded for now:

- Natural-language rule parsing.
- LLM-based SQL generation.
- SQLGlot AST validation against AI-generated SQL.
- Human approval UI.
- Cron-based long-term scheduling.
- Full report generation UI.
- Email, Slack, or dashboard notifications.
- Production authentication and authorization.

---

## 3. High-Level Architecture

The initial system has four main parts:

```text
User / Tester
    |
    v
FastAPI Test API
    |
    v
Rule Execution Daemon
    |
    v
PostgreSQL Test Database
    |
    v
JSON Result Response
```

The user provides a SQL validation query directly to the API.

The daemon executes the query against PostgreSQL and returns a structured JSON result.

The SQL should return one aggregate value, usually either:

```sql
SELECT COUNT(*) AS violation_count ...
```

or:

```sql
SELECT COUNT(*) AS observed_value ...
```

The daemon should not return raw business rows. It should only return aggregate results.

---

## 4. Core Design Principle

The daemon follows the platform's main architectural philosophy:

> Push the validation computation down into PostgreSQL and return only aggregate results to the application.

The daemon should never pull millions of database rows into Python memory.

Instead, PostgreSQL performs the validation work, and the daemon receives only a small scalar result such as:

```json
{
  "violation_count": 0
}
```

or:

```json
{
  "observed_value": 1250
}
```

---

## 5. Component Responsibilities

## 5.1 FastAPI Test API

The API is a temporary testing interface.

It accepts SQL directly from the user and returns the daemon's result.

Suggested endpoint:

```http
POST /rules/run
```

Example request:

```json
{
  "rule_name": "Active employees must not have negative salaries",
  "sql": "SELECT COUNT(*) AS violation_count FROM employees WHERE status = 'active' AND salary < 0;",
  "expected_result": {
    "type": "zero_violations"
  }
}
```

Example response:

```json
{
  "rule_name": "Active employees must not have negative salaries",
  "status": "PASS",
  "result": {
    "violation_count": 0
  },
  "execution_time_ms": 42,
  "error": null
}
```

The API should be thin. Its responsibilities are:

- Validate the request shape.
- Forward the SQL and rule metadata to the daemon/execution service.
- Return the daemon's JSON response.
- Avoid implementing final production reporting logic.

---

## 5.2 Rule Execution Daemon

The daemon is the core part of this milestone.

For now, the daemon can be implemented as a Python module/service invoked by the API.

Later, it can evolve into a scheduled background worker that reads persisted rules from the database.

Current responsibilities:

1. Accept a rule execution request.
2. Validate that the SQL is acceptable for testing.
3. Open a pooled PostgreSQL connection.
4. Start a read-only transaction.
5. Set a hard statement timeout.
6. Execute the aggregate SQL query.
7. Read the scalar result.
8. Evaluate pass/fail logic.
9. Return structured JSON.
10. Log execution metadata.

Suggested Python module name:

```text
app/daemon/executor.py
```

Suggested main function:

```python
async def execute_rule(rule: RuleExecutionRequest) -> RuleExecutionResult:
    ...
```

The daemon should be designed so that scheduling can be added later without rewriting the execution engine.

---

## 5.3 PostgreSQL Test Database

A local PostgreSQL database should be created using Docker Compose.

It should contain test schemas and bulk data.

Suggested schemas:

```sql
CREATE SCHEMA IF NOT EXISTS business_data;
CREATE SCHEMA IF NOT EXISTS dq_config;
CREATE SCHEMA IF NOT EXISTS dq_results;
```

Suggested test tables:

```sql
CREATE TABLE business_data.employees (
    employee_id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    status TEXT NOT NULL,
    salary NUMERIC(12, 2),
    department TEXT,
    hired_at DATE NOT NULL
);

CREATE TABLE business_data.students (
    student_id BIGSERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    enrollment_date DATE NOT NULL,
    admission_status TEXT NOT NULL,
    grade_level TEXT
);

CREATE TABLE dq_results.test_results (
    result_id BIGSERIAL PRIMARY KEY,
    rule_name TEXT NOT NULL,
    sql_text TEXT NOT NULL,
    status TEXT NOT NULL,
    observed_key TEXT,
    observed_value NUMERIC,
    execution_time_ms INTEGER,
    error_message TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Bulk sample data should be inserted for testing.

Example employee scenarios:

- Active employees with valid positive salaries.
- Active employees with negative salaries.
- Inactive employees with negative salaries.
- Employees with null salaries.
- Employees across multiple departments.

Example student scenarios:

- More than 1000 enrolled students in one year.
- Fewer than 1000 enrolled students in another year.
- Rejected or cancelled admissions.
- Students across multiple enrollment dates.

---

## 5.4 Docker/Linux Runtime

The daemon must run in a Linux environment.

Use Docker and Docker Compose for local development and portability.

Suggested services:

```yaml
services:
  api:
    build: .
    container_name: dq_api
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql+asyncpg://dq_executor:${DQ_EXECUTOR_PASSWORD}@postgres:5432/dq_test
    ports:
      - "8000:8000"

  postgres:
    image: postgres:16
    container_name: dq_postgres
    environment:
      POSTGRES_DB: dq_test
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"
    volumes:
      - ./db/init:/docker-entrypoint-initdb.d
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

The API container should run on Linux and expose FastAPI on port `8000`.

Suggested API startup command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 6. Rule Input Model

For testing, the API accepts SQL directly.

Suggested request model:

```json
{
  "rule_name": "string",
  "sql": "string",
  "expected_result": {
    "type": "zero_violations | min_threshold | max_threshold | equals",
    "value": 0
  }
}
```

### Supported Rule Evaluation Types

## 6.1 Zero Violations

Used for queries that return `violation_count`.

Example:

```sql
SELECT COUNT(*) AS violation_count
FROM business_data.employees
WHERE status = 'active'
  AND salary < 0;
```

Evaluation:

```text
PASS if violation_count = 0
FAIL if violation_count > 0
```

Request:

```json
{
  "rule_name": "No active employee has negative salary",
  "sql": "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE status = 'active' AND salary < 0;",
  "expected_result": {
    "type": "zero_violations"
  }
}
```

---

## 6.2 Minimum Threshold

Used for aggregate checks such as minimum yearly enrollment.

Example:

```sql
SELECT COUNT(*) AS observed_value
FROM business_data.students
WHERE enrollment_date >= DATE '2026-01-01'
  AND enrollment_date < DATE '2027-01-01'
  AND admission_status = 'enrolled';
```

Evaluation:

```text
PASS if observed_value >= expected_result.value
FAIL if observed_value < expected_result.value
```

Request:

```json
{
  "rule_name": "At least 1000 students enrolled in 2026",
  "sql": "SELECT COUNT(*) AS observed_value FROM business_data.students WHERE enrollment_date >= DATE '2026-01-01' AND enrollment_date < DATE '2027-01-01' AND admission_status = 'enrolled';",
  "expected_result": {
    "type": "min_threshold",
    "value": 1000
  }
}
```

---

## 6.3 Maximum Threshold

Used for checks where the aggregate result should not exceed a limit.

Example:

```sql
SELECT COUNT(*) AS observed_value
FROM business_data.employees
WHERE salary IS NULL;
```

Evaluation:

```text
PASS if observed_value <= expected_result.value
FAIL if observed_value > expected_result.value
```

---

## 6.4 Equals

Used when the result must exactly equal a given value.

Example:

```sql
SELECT COUNT(*) AS observed_value
FROM business_data.employees
WHERE department = 'Engineering';
```

Evaluation:

```text
PASS if observed_value = expected_result.value
FAIL otherwise
```

---

## 7. Expected SQL Contract

For the current milestone, the SQL submitted to the API should follow these rules:

1. It must be a single SQL statement.
2. It must be a `SELECT` query.
3. It must return exactly one row.
4. It should return exactly one aggregate column.
5. The returned column should be named either:
   - `violation_count`
   - `observed_value`
6. It must not return raw business rows.
7. It must not contain mutation statements such as:
   - `INSERT`
   - `UPDATE`
   - `DELETE`
   - `DROP`
   - `ALTER`
   - `TRUNCATE`
   - `CREATE`
8. It must not call unsafe functions.
9. It must run under the configured statement timeout.

Even though full SQLGlot AST validation is part of the broader platform, the test API should still implement a basic SQL safety check.

Recommended basic guardrails:

- Strip comments.
- Reject semicolon-separated multiple statements.
- Parse SQL with SQLGlot if available.
- Confirm root expression is `SELECT`.
- Reject known dangerous keywords.
- Enforce a single-row aggregate result in runtime validation.

---

## 8. Database Security Controls

The daemon should not connect as the PostgreSQL superuser.

Create a restricted execution role:

```sql
CREATE ROLE dq_executor LOGIN PASSWORD :'dq_executor_password';

GRANT USAGE ON SCHEMA business_data TO dq_executor;
GRANT SELECT ON ALL TABLES IN SCHEMA business_data TO dq_executor;

GRANT USAGE ON SCHEMA dq_results TO dq_executor;
GRANT INSERT ON dq_results.test_results TO dq_executor;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dq_results TO dq_executor;
```

The daemon should connect using `dq_executor`, not `postgres`.

Every rule execution should use:

```sql
SET LOCAL statement_timeout = '15s';
SET TRANSACTION READ ONLY;
```

Recommended execution pattern:

```sql
BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
-- execute validation SELECT
COMMIT;
```

If the query exceeds the timeout, PostgreSQL should cancel the statement and the daemon should return an `ERROR` result.

---

## 9. Connection Management

Use SQLAlchemy connection pooling.

Recommended stack:

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy 2.x
- asyncpg
- Pydantic
- PostgreSQL 16
- Docker Compose

Suggested pool settings:

```text
pool_size = 5
max_overflow = 5
pool_timeout = 30
pool_recycle = 1800
```

This prevents opening too many simultaneous database connections.

Later, when scheduling is added, execution jitter can be used to prevent many validations from hitting the database at the exact same second.

---

## 10. Result Model

Suggested JSON result format:

```json
{
  "rule_name": "No active employee has negative salary",
  "status": "PASS",
  "result": {
    "violation_count": 0
  },
  "expected_result": {
    "type": "zero_violations"
  },
  "execution_time_ms": 42,
  "executed_at": "2026-05-09T10:00:00Z",
  "error": null
}
```

Failure example:

```json
{
  "rule_name": "No active employee has negative salary",
  "status": "FAIL",
  "result": {
    "violation_count": 3
  },
  "expected_result": {
    "type": "zero_violations"
  },
  "execution_time_ms": 39,
  "executed_at": "2026-05-09T10:00:00Z",
  "error": null
}
```

Error example:

```json
{
  "rule_name": "Broken SQL rule",
  "status": "ERROR",
  "result": null,
  "expected_result": {
    "type": "zero_violations"
  },
  "execution_time_ms": 5,
  "executed_at": "2026-05-09T10:00:00Z",
  "error": {
    "type": "SQL_EXECUTION_ERROR",
    "message": "relation business_data.unknown_table does not exist"
  }
}
```

---

## 11. Result Persistence

Each rule execution should be inserted into:

```text
dq_results.test_results
```

Suggested insert fields:

- `rule_name`
- `sql_text`
- `status`
- `observed_key`
- `observed_value`
- `execution_time_ms`
- `error_message`
- `executed_at`

The API response should be returned immediately, and the same result should be persisted for inspection.

---

## 12. Suggested Project Structure

```text
dq-daemon/
  app/
    __init__.py
    main.py
    api/
      __init__.py
      routes.py
    daemon/
      __init__.py
      executor.py
      evaluator.py
      sql_safety.py
    db/
      __init__.py
      session.py
    models/
      __init__.py
      requests.py
      responses.py
    settings.py

  db/
    init/
      001_create_schemas.sql
      002_create_tables.sql
      003_create_roles.sh
      004_seed_data.sql

  tests/
    test_executor.py
    test_evaluator.py
    test_sql_safety.py

  Dockerfile
  docker-compose.yml
  requirements.txt
  README.md
```

---

## 13. Execution Flow

```text
1. Tester sends POST /rules/run with SQL and expected result.
2. API validates request body.
3. API calls daemon executor.
4. Executor validates SQL shape.
5. Executor opens pooled DB connection.
6. Executor starts read-only transaction.
7. Executor sets statement timeout.
8. Executor runs aggregate SELECT.
9. Executor receives one scalar value.
10. Evaluator determines PASS / FAIL.
11. Executor writes result into dq_results.test_results.
12. API returns JSON response.
```

---

## 14. Example API Calls

## 14.1 Zero-Violation Rule

```bash
curl -X POST http://localhost:8000/rules/run \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "No active employee has negative salary",
    "sql": "SELECT COUNT(*) AS violation_count FROM business_data.employees WHERE status = '''active''' AND salary < 0;",
    "expected_result": {
      "type": "zero_violations"
    }
  }'
```

---

## 14.2 Minimum Threshold Rule

```bash
curl -X POST http://localhost:8000/rules/run \
  -H "Content-Type: application/json" \
  -d '{
    "rule_name": "At least 1000 students enrolled in 2026",
    "sql": "SELECT COUNT(*) AS observed_value FROM business_data.students WHERE enrollment_date >= DATE '''2026-01-01''' AND enrollment_date < DATE '''2027-01-01''' AND admission_status = '''enrolled''';",
    "expected_result": {
      "type": "min_threshold",
      "value": 1000
    }
  }'
```

---

## 15. Initial Test Data Requirements

The seed script should generate enough data to test performance and rule outcomes.

Suggested volume:

- 100,000 employees.
- 10,000 students.
- A controlled number of intentional data quality violations.

Example intentional violations:

```text
employees:
- 10 active employees with salary < 0
- 25 active employees with salary IS NULL
- 100 inactive employees with salary < 0

students:
- 1,200 enrolled students in 2026
- 850 enrolled students in 2025
- 100 cancelled admissions in 2026
```

Using PostgreSQL `generate_series` is recommended for bulk inserts.

Example:

```sql
INSERT INTO business_data.employees (
    full_name,
    status,
    salary,
    department,
    hired_at
)
SELECT
    'Employee ' || gs,
    CASE WHEN gs % 10 = 0 THEN 'inactive' ELSE 'active' END,
    CASE
        WHEN gs <= 10 THEN -1000
        WHEN gs > 10 AND gs <= 35 THEN NULL
        ELSE 50000 + (gs % 10000)
    END,
    CASE
        WHEN gs % 4 = 0 THEN 'Engineering'
        WHEN gs % 4 = 1 THEN 'Sales'
        WHEN gs % 4 = 2 THEN 'Finance'
        ELSE 'Operations'
    END,
    DATE '2020-01-01' + ((gs % 1500) * INTERVAL '1 day')
FROM generate_series(1, 100000) AS gs;
```

---

## 16. Error Handling

The daemon should return `ERROR` for:

- Invalid SQL.
- SQL with disallowed statements.
- SQL returning zero rows.
- SQL returning more than one row.
- SQL returning more than one column.
- SQL result not numeric.
- Database timeout.
- Database connection failure.
- Permission denied.
- Unknown runtime error.

Errors should be structured.

Example:

```json
{
  "status": "ERROR",
  "error": {
    "type": "INVALID_SQL",
    "message": "Only single-statement SELECT queries are allowed."
  }
}
```

---

## 17. Minimal Safety Checklist

Before executing SQL:

- [ ] Confirm only one statement is present.
- [ ] Confirm the statement is a `SELECT`.
- [ ] Reject mutation and DDL keywords.
- [ ] Ensure the query is executed as `dq_executor`.
- [ ] Use a read-only transaction.
- [ ] Set `statement_timeout`.
- [ ] Enforce scalar aggregate output.
- [ ] Never return raw table rows.
- [ ] Persist result metadata.
- [ ] Return structured JSON.

---

## 18. Future Extensions

After this milestone works, future teammates can add:

1. Rule registry table: `dq_config.dq_rules`.
2. Cron schedules and APScheduler.
3. Natural-language input.
4. LLM-generated SQL.
5. LLM-generated plain-English interpretation.
6. SQLGlot AST validation.
7. Human approval workflow.
8. Full report generation.
9. Alerting and notifications.
10. Multi-tenant security controls.
11. Rule versioning.
12. Query cost estimation with `EXPLAIN`.
13. Read replica execution.
14. Web dashboard.

---

## 19. Codex Build Instructions

Implement the first version of the system using this architecture.

The priority order should be:

1. Create Docker Compose with PostgreSQL and API services.
2. Create database schemas, tables, roles, and seed data.
3. Implement FastAPI request and response models.
4. Implement `/rules/run`.
5. Implement daemon executor with pooled PostgreSQL access.
6. Implement SQL safety validation.
7. Implement pass/fail evaluator.
8. Persist results into `dq_results.test_results`.
9. Add basic tests.
10. Document how to run locally.

The system should be runnable with:

```bash
docker compose up --build
```

The API should be available at:

```text
http://localhost:8000
```

The primary test endpoint should be:

```text
POST /rules/run
```

---

## 20. Final Summary

The current milestone is to build a Dockerized Linux-compatible Data Quality Daemon test harness.

The user will provide SQL directly.

The daemon will safely execute the SQL inside PostgreSQL, evaluate the aggregate result, persist execution metadata, and return a JSON pass/fail/error response.

This creates the execution foundation that the later LLM rule-generation and reporting layers can build upon.
