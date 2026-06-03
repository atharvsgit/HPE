# HPE Data Quality Platform

AI-assisted data quality platform for connecting PostgreSQL databases, generating validation jobs from natural language, orchestrating scheduled checks, storing results, and sending Slack/email alerts.

## What Is Built

- FastAPI backend for databases, AI planning, saved jobs, results, alerts, and settings.
- React/Vite frontend with Dashboard, Databases, AI Command, Jobs, Alerts, and Settings.
- PostgreSQL metadata store plus seeded demo business data.
- Redis and Celery worker for intelligent alert processing.
- APScheduler daemon for recurring validation jobs.
- Slack and SMTP email notifications for failed/error rules.
- Gemini-first AI planning with provider settings for Gemini, OpenAI, Claude/Anthropic, OpenRouter, and Groq.
- Internal heuristic fallback when no AI key is configured.

## Tech Stack

- Backend: Python, FastAPI, SQLAlchemy async, asyncpg, APScheduler, Celery, Redis.
- Database: PostgreSQL 16 with `business_data`, `dq_config`, and `dq_results` schemas.
- AI: Google Gemini via `google-genai`; optional OpenAI-compatible providers through HTTP.
- Monitoring and alerts: Slack incoming webhooks, SMTP email, persisted notification delivery logs.
- Frontend: React, Vite, Axios, TailwindCSS/CSS tokens.
- Runtime: Docker Compose.

## Local Secrets

Use `.env.local` for local secrets. It is ignored by Git.

Never commit:

- `.env`
- `.env.local`
- API keys
- SMTP passwords
- Slack webhooks
- Docker database passwords

Recommended `.env.local` shape:

```env
POSTGRES_DB=dq_test
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change_this_locally
DQ_EXECUTOR_PASSWORD=change_this_locally
DQ_APP_PASSWORD=change_this_locally

RULE_EXECUTION_JITTER_SECONDS=0
PREFECT_SERVER_ALLOW_EPHEMERAL_MODE=true

SLACK_WEBHOOK_URL=
SLACK_BOT_TOKEN=
SLACK_CHANNEL=

SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=5
NOTIFICATION_HTTP_TIMEOUT_SECONDS=5
NOTIFICATION_EMAIL_FROM=alerts@dataqualitydaemon.local
ADMIN_EMAIL=

GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
RULE_SUGGESTION_BACKEND=gemini

LLM_ENABLED=false
LLM_MODEL=llama3-8b-8192
GROQ_API_KEY=

PROFILING_ROW_LIMIT=100000
ANOMALY_CONTAMINATION=0.05
VITE_AI_RULE_BUILDER_ENABLED=false
```

For Gmail, `SMTP_PASSWORD` must be a Google App Password, not the normal account password.

## Run Locally

If Docker is installed but not on PATH in PowerShell:

```powershell
$env:PATH = 'C:\Program Files\Docker\Docker\resources\bin;' + $env:PATH
```

Start backend services:

```powershell
docker compose --env-file .env.local up --build -d
```

Start frontend:

```powershell
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
Frontend: http://127.0.0.1:5173
Backend:  http://127.0.0.1:8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Demo Flow

1. Open the frontend.
2. Go to **Settings** and confirm AI, Slack, and email are configured.
3. Go to **Databases** and confirm `Docker Demo Postgres` is connected.
4. Go to **AI Command** and enter:

```text
Check salary less than 10000 in employees and alert on Slack and email
```

5. Generate the plan, review the SQL, then approve it.
6. Go to **Jobs** and click **Run Now**.
7. Go to **Alerts** and confirm the failure event and notification delivery logs.

Expected demo result on seeded data:

- Status: `FAIL`
- Violation count: `110`
- Slack delivery: `sent`
- Email delivery: `sent` when SMTP is configured correctly

## Main APIs

Product workspace:

- `GET /dashboard/summary`
- `GET /databases`
- `POST /databases`
- `POST /databases/{id}/test`
- `GET /databases/{id}/schema`
- `POST /assistant/plan`
- `POST /assistant/approve`
- `GET /orchestrator/jobs`
- `POST /orchestrator/jobs`
- `PATCH /orchestrator/jobs/{id}`
- `POST /orchestrator/jobs/{id}/run`
- `POST /orchestrator/jobs/{id}/pause`
- `POST /orchestrator/jobs/{id}/resume`
- `DELETE /orchestrator/jobs/{id}`
- `GET /alerts`
- `GET /notifications`
- `GET /settings`
- `PATCH /settings/ai`
- `PATCH /settings/notifications`

Legacy rule APIs are still available under `/rules/*`.

## SQL Rule Contract

Validation SQL must be:

- one `SELECT` statement
- read-only
- one row
- one numeric aggregate column named `violation_count` or `observed_value`

Example:

```sql
SELECT COUNT(*) AS violation_count
FROM business_data.employees
WHERE salary < 10000;
```

The backend rejects obvious destructive SQL before saving or running rules. Execution uses restricted database roles and statement timeouts.

## Docker Services

- `dq_postgres`: metadata and demo business database.
- `dq_redis`: broker for async alert processing.
- `dq_api`: FastAPI backend.
- `dq_scheduler`: recurring job scheduler.
- `dq_dispatcher`: intelligent alert dispatcher.
- `dq_llm_worker`: Celery worker for optional LLM enrichment.

Useful commands:

```powershell
docker compose --env-file .env.local ps
docker logs dq_api --tail 100
docker compose --env-file .env.local restart api scheduler dispatcher llm_worker
docker compose --env-file .env.local down
```

Reset database volume only when you intentionally want fresh seed data:

```powershell
docker compose --env-file .env.local down -v
docker compose --env-file .env.local up --build -d
```

## Tests

Backend:

```powershell
python -m compileall -q app tests
python -m pytest -q
```

Frontend:

```powershell
npm run build -- --mode production
```

Docker smoke:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/settings
Invoke-RestMethod http://127.0.0.1:8000/dashboard/summary
```

## Notes For Contributors

- Keep `.env.example` sanitized.
- Keep real secrets only in `.env.local` or saved runtime settings in local Postgres.
- Do not commit `dist/`, `node_modules/`, Docker volumes, or logs.
- If a secret was shared accidentally, rotate it before using the repository in a public or shared setting.
