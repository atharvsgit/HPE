from __future__ import annotations

import json
import re
from typing import Any

import httpx
from sqlalchemy import text

from app.daemon.sql_safety import SQLSafetyError
from app.db.session import metadata_engine
from app.models.product import AssistantPlanRequest, AssistantPlanResponse
from app.models.requests import ExpectedResult
from app.services.ai_rules.validator import validate_ai_generated_sql
from app.services.database_connections import (
    get_connection_row,
    get_database_schema,
    list_database_connections,
    target_engine,
)
from app.services.schedule_parser import parse_schedule_to_cron
from app.services.runtime_settings import RuntimeAISettings, get_runtime_ai_settings


async def create_assistant_plan(request: AssistantPlanRequest) -> AssistantPlanResponse:
    database_id = request.database_id or await _default_database_id()
    database_row = await get_connection_row(database_id)
    if database_row is None:
        raise ValueError("No database connection found. Add a database first.")

    schema = await get_database_schema(database_id)
    ai_settings = await get_runtime_ai_settings()
    raw_plan = await _plan_with_provider(request.prompt, schema.model_dump(), database_row, ai_settings)
    source = ai_settings.provider
    if raw_plan is None:
        raw_plan = _plan_with_heuristics(request.prompt, schema.model_dump(), database_row)
        source = "heuristic"

    sql = str(raw_plan["sql"]).strip().rstrip(";")
    validate_ai_generated_sql(sql)
    dry_run = await _dry_run_sql(database_id, sql)
    generation_id = await _log_generation(request.prompt, raw_plan, source)

    return AssistantPlanResponse(
        generation_id=generation_id,
        database_id=database_id,
        database_name=database_row["name"],
        table_name=raw_plan["table_name"],
        rule_name=raw_plan["rule_name"],
        sql=sql,
        expected_result=ExpectedResult(**raw_plan.get("expected_result", {"type": "zero_violations"})),
        schedule_text=raw_plan.get("schedule_text") or "manual",
        schedule_cron=raw_plan.get("schedule_cron"),
        severity=raw_plan.get("severity", "critical"),
        notification_channels=raw_plan.get("notification_channels") or ["slack"],
        explanation=raw_plan.get("explanation", "Generated from the natural language command."),
        confidence=raw_plan.get("confidence", "medium"),
        source=source,
        dry_run=dry_run,
    )


async def _default_database_id() -> int:
    connections = await list_database_connections()
    if not connections:
        raise ValueError("No database connections exist.")
    connected = next((item for item in connections if item.status == "connected"), None)
    return (connected or connections[0]).id


async def _plan_with_provider(
    prompt: str,
    schema_payload: dict[str, Any],
    database_row: dict[str, Any],
    ai_settings: RuntimeAISettings,
) -> dict[str, Any] | None:
    if not ai_settings.api_key:
        return None
    planner_prompt = _planner_prompt(prompt, schema_payload, database_row)
    if ai_settings.provider == "gemini":
        return await _plan_with_gemini(planner_prompt, ai_settings)
    return await _plan_with_chat_provider(planner_prompt, ai_settings)


async def _plan_with_gemini(
    planner_prompt: str,
    ai_settings: RuntimeAISettings,
) -> dict[str, Any] | None:
    try:
        from google import genai  # type: ignore[import-untyped]
    except ImportError:
        return None

    try:
        client = genai.Client(api_key=ai_settings.api_key)
        response = client.models.generate_content(
            model=ai_settings.model,
            contents=planner_prompt,
        )
        return _parse_json_object(response.text)
    except Exception:
        return None


async def _plan_with_chat_provider(
    planner_prompt: str,
    ai_settings: RuntimeAISettings,
) -> dict[str, Any] | None:
    headers = {"Content-Type": "application/json"}
    payload: dict[str, Any]
    endpoint: str

    if ai_settings.provider == "anthropic":
        endpoint = "https://api.anthropic.com/v1/messages"
        headers.update({
            "x-api-key": ai_settings.api_key,
            "anthropic-version": "2023-06-01",
        })
        payload = {
            "model": ai_settings.model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": planner_prompt}],
        }
    else:
        endpoint = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "openrouter": "https://openrouter.ai/api/v1/chat/completions",
            "groq": "https://api.groq.com/openai/v1/chat/completions",
        }.get(ai_settings.provider, "")
        if not endpoint:
            return None
        headers["Authorization"] = f"Bearer {ai_settings.api_key}"
        payload = {
            "model": ai_settings.model,
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": planner_prompt},
            ],
            "temperature": 0.1,
        }
        if ai_settings.provider == "openai":
            payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        if ai_settings.provider == "anthropic":
            text_response = data["content"][0]["text"]
        else:
            text_response = data["choices"][0]["message"]["content"]
        return _parse_json_object(text_response)
    except Exception:
        return None


def _planner_prompt(
    prompt: str,
    schema_payload: dict[str, Any],
    database_row: dict[str, Any],
) -> str:
    planner_prompt = f"""
You are a data quality job planner for PostgreSQL. Convert the user command into strict JSON.

Database name: {database_row["name"]}
Available schema:
{json.dumps(schema_payload, indent=2)}

Rules:
- Choose one table from the schema.
- Generate a SELECT-only SQL query returning one numeric column aliased as violation_count.
- The SQL must count rows that violate the user's requested condition.
- Normalize the requested schedule into a 5-field cron expression when possible.
- Use severity critical when the user asks for alerts or reports.
- Return JSON only, no markdown.

JSON shape:
{{
  "table_name": "schema.table",
  "rule_name": "short name",
  "sql": "SELECT COUNT(*) AS violation_count FROM schema.table WHERE ...",
  "expected_result": {{"type": "zero_violations"}},
  "schedule_text": "original/normalized schedule",
  "schedule_cron": "* * * * * or null",
  "severity": "critical|high|medium|low",
  "notification_channels": ["slack"],
  "explanation": "short explanation",
  "confidence": "high|medium|low"
}}

User command: {prompt}
"""
    return planner_prompt


def _plan_with_heuristics(
    prompt: str,
    schema_payload: dict[str, Any],
    database_row: dict[str, Any],
) -> dict[str, Any]:
    text_prompt = prompt.lower()
    tables = schema_payload.get("tables", [])
    if not tables:
        raise ValueError("No tables found in the selected database.")

    table = _choose_table(text_prompt, tables)
    column = _choose_column(text_prompt, table)
    operator, value = _condition_from_prompt(text_prompt, column)
    table_name = table["qualified_name"]
    schedule_text = _schedule_text_from_prompt(text_prompt)
    schedule_cron = parse_schedule_to_cron(schedule_text)
    severity = "critical" if "alert" in text_prompt or "slack" in text_prompt or "report" in text_prompt else "medium"

    if operator == "not_null":
        where_clause = f"{_quote(column['name'])} IS NULL"
        rule_name = f"{column['name']} not null check"
    elif isinstance(value, str):
        escaped = value.replace("'", "''")
        where_clause = f"{_quote(column['name'])} {operator} '{escaped}'"
        rule_name = f"{column['name']} value check"
    else:
        where_clause = f"{_quote(column['name'])} {operator} {value}"
        rule_name = f"{column['name']} threshold check"

    return {
        "table_name": table_name,
        "rule_name": rule_name,
        "sql": f"SELECT COUNT(*) AS violation_count FROM {_quote_qualified(table_name)} WHERE {where_clause}",
        "expected_result": {"type": "zero_violations"},
        "schedule_text": schedule_text,
        "schedule_cron": schedule_cron,
        "severity": severity,
        "notification_channels": ["slack"] if "slack" in text_prompt or "alert" in text_prompt else ["slack"],
        "explanation": f"Counts rows in {table_name} where {column['name']} violates the requested condition.",
        "confidence": "medium",
    }


def _choose_table(text_prompt: str, tables: list[dict[str, Any]]) -> dict[str, Any]:
    for table in tables:
        names = {
            table["qualified_name"].lower(),
            table["table_name"].lower(),
            table["table_name"].lower().rstrip("s"),
        }
        if any(name in text_prompt for name in names):
            return table
    return tables[0]


def _choose_column(text_prompt: str, table: dict[str, Any]) -> dict[str, Any]:
    for column in table.get("columns", []):
        if column["name"].lower() in text_prompt:
            return column
    for column in table.get("columns", []):
        if any(word in column["name"].lower() for word in text_prompt.split()):
            return column
    return table.get("columns", [])[0]


def _condition_from_prompt(text_prompt: str, column: dict[str, Any]) -> tuple[str, int | float | str | None]:
    if "not null" in text_prompt or "never be null" in text_prompt or "should not be null" in text_prompt:
        return "not_null", None
    if "negative" in text_prompt:
        return "<", 0

    number = _first_number(text_prompt)
    if any(term in text_prompt for term in ["less than", "below", "under", "<"]):
        return "<", number or 0
    if any(term in text_prompt for term in ["greater than", "above", "over", ">"]):
        return ">", number or 0
    if any(term in text_prompt for term in ["equals", "equal to", "is "]):
        quoted = re.search(r"['\"]([^'\"]+)['\"]", text_prompt)
        return "=", quoted.group(1) if quoted else (number or "")
    return "<", number or 0


def _schedule_text_from_prompt(text_prompt: str) -> str:
    match = re.search(r"every\s+((?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)?\s*(?:minute|minutes|hour|hours|day|days|week|weeks|month|months))", text_prompt)
    if match:
        return f"every {match.group(1).strip()}"
    for word in ("daily", "weekly", "monthly"):
        if word in text_prompt:
            return word
    return "manual"


def _first_number(text_prompt: str) -> int | None:
    match = re.search(r"\b(\d+)\b", text_prompt)
    if match:
        return int(match.group(1))
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10}
    for word, value in words.items():
        if re.search(rf"\b{word}\b", text_prompt):
            return value
    return None


async def _dry_run_sql(database_id: int, sql: str) -> dict[str, Any]:
    async with target_engine(database_id) as engine:
        async with engine.connect() as conn:
            rows = (await conn.execute(text(f"SELECT * FROM ({sql}) AS plan_check LIMIT 2"))).mappings().all()
    if len(rows) != 1:
        raise SQLSafetyError("Generated SQL must return exactly one row.", "AI_RESULT_SHAPE")
    row = dict(rows[0])
    return {"row": row}


async def _log_generation(prompt: str, plan: dict[str, Any], source: str) -> int | None:
    try:
        async with metadata_engine.begin() as conn:
            return (await conn.execute(
                text("""
                    INSERT INTO dq_results.ai_rule_generations
                        (prompt, original_prompt, generated_sql, explanation, assumptions,
                         possible_edge_cases, confidence, provider_name, model_name,
                         prompt_version, parsing_failure)
                    VALUES
                        (:prompt, :prompt, :sql, :explanation, '[]', '[]',
                         :confidence, :provider_name, :model_name, 'revamp-v1', false)
                    RETURNING id
                """),
                {
                    "prompt": prompt,
                    "sql": plan.get("sql"),
                    "explanation": plan.get("explanation"),
                    "confidence": plan.get("confidence", "medium"),
                    "provider_name": source,
                    "model_name": source,
                },
            )).scalar_one()
    except Exception:
        return None


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Gemini response did not include JSON.")
    return json.loads(cleaned[start : end + 1])


def _quote(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'


def _quote_qualified(value: str) -> str:
    return ".".join(_quote(part) for part in value.split("."))
