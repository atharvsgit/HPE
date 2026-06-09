from __future__ import annotations

import json
import re
import asyncio
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

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
from app.services.schedule_preview import build_schedule_preview
from app.services.runtime_settings import RuntimeAISettings, get_runtime_ai_settings
from app.settings import get_settings


PROMPT_INJECTION_PHRASES = {
    "ignore previous instructions",
    "system prompt",
    "system command",
    "you are now",
    "developer message",
    "drop table",
    "delete all",
    "always pass",
}


async def create_assistant_plan(request: AssistantPlanRequest) -> AssistantPlanResponse:
    _reject_prompt_injection(request.prompt)
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
    else:
        raw_plan = _apply_prompt_overrides(raw_plan, request.prompt, schema.model_dump())

    raw_schedule_cron = raw_plan.get("schedule_cron")
    schedule_cron = str(raw_schedule_cron).strip() if raw_schedule_cron is not None else None
    if schedule_cron == "":
        schedule_cron = None
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
        schedule_cron=schedule_cron,
        severity=raw_plan.get("severity", "critical"),
        notification_channels=raw_plan.get("notification_channels") or ["slack"],
        explanation=raw_plan.get("explanation", "Generated from the natural language command."),
        confidence=raw_plan.get("confidence", "medium"),
        source=source,
        dry_run=dry_run,
        schedule_preview=build_schedule_preview(schedule_cron),
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
        return await asyncio.wait_for(
            asyncio.to_thread(_generate_gemini_plan, genai, planner_prompt, ai_settings),
            timeout=get_settings().ai_planner_timeout_seconds,
        )
    except (TimeoutError, Exception):
        return None


def _generate_gemini_plan(genai: Any, planner_prompt: str, ai_settings: RuntimeAISettings) -> dict[str, Any]:
    client = genai.Client(api_key=ai_settings.api_key)
    response = client.models.generate_content(
        model=ai_settings.model,
        contents=planner_prompt,
    )
    return _parse_json_object(response.text)


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
        async with httpx.AsyncClient(timeout=get_settings().ai_planner_timeout_seconds) as client:
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
- For completeness checks such as "has a column/value" or "column is present", count rows where the column IS NULL.
- Respect explicitly named table and column phrases from the user command. Treat spaces/plurals as matching underscores, e.g. "grade levels" means "grade_level" when that column exists.
- For future-date checks, count rows where the date/timestamp column is greater than CURRENT_DATE.
- Normalize the requested schedule into a 5-field cron expression when possible.
- Use severity critical when the user asks for alerts or reports.
- Include "email" in notification_channels when the user asks for email, mail, or e-mail. Include "slack" when the user asks for Slack.
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
  "notification_channels": ["slack", "email"],
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
    text_prompt = _normalize_prompt(prompt.lower())
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
    notification_channels = _notification_channels_from_prompt(text_prompt) or ["slack"]

    if operator == "not_null":
        where_clause = f"{_quote(column['name'])} IS NULL"
        rule_name = f"{column['name']} not null check"
    elif operator == "future_date":
        where_clause = f"{_quote(column['name'])} > CURRENT_DATE"
        rule_name = f"{column['name']} future date check"
    elif operator == "outside_between" and isinstance(value, tuple):
        low_value, high_value = value
        where_clause = f"({_quote(column['name'])} < {low_value} OR {_quote(column['name'])} > {high_value})"
        rule_name = f"{column['name']} range check"
    elif operator == "inside_between" and isinstance(value, tuple):
        low_value, high_value = value
        where_clause = f"{_quote(column['name'])} BETWEEN {low_value} AND {high_value}"
        rule_name = f"{column['name']} excluded range check"
    elif operator == "not_equals" and isinstance(value, str):
        escaped = value.replace("'", "''")
        where_clause = f"{_quote(column['name'])} <> '{escaped}'"
        rule_name = f"{column['name']} expected value check"
    elif operator == "not_equals":
        where_clause = f"{_quote(column['name'])} <> {value}"
        rule_name = f"{column['name']} expected value check"
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
        "notification_channels": notification_channels,
        "explanation": f"Counts rows in {table_name} where {column['name']} violates the requested condition.",
        "confidence": "medium",
    }


def _apply_prompt_overrides(
    raw_plan: dict[str, Any],
    prompt: str,
    schema_payload: dict[str, Any],
) -> dict[str, Any]:
    text_prompt = _normalize_prompt(prompt.lower())
    normalized_plan = dict(raw_plan)

    channels = _notification_channels_from_prompt(text_prompt)
    if channels:
        normalized_plan["notification_channels"] = channels
        if "alert" in text_prompt or "slack" in channels or "email" in channels:
            normalized_plan["severity"] = "critical"

    schedule_text = _schedule_text_from_prompt(text_prompt)
    if schedule_text != "manual":
        normalized_plan["schedule_text"] = schedule_text
        normalized_plan["schedule_cron"] = parse_schedule_to_cron(schedule_text)

    tables = schema_payload.get("tables", [])
    if not tables:
        return normalized_plan

    table = _choose_table(text_prompt, tables)
    column, score = _choose_column_with_score(text_prompt, table)
    if score < 50:
        return normalized_plan

    operator, value = _condition_from_prompt(text_prompt, column)
    if operator != "not_null":
        return normalized_plan

    table_name = table["qualified_name"]
    normalized_plan.update(
        {
            "table_name": table_name,
            "rule_name": f"{column['name']} not null check",
            "sql": (
                f"SELECT COUNT(*) AS violation_count "
                f"FROM {_quote_qualified(table_name)} "
                f"WHERE {_quote(column['name'])} IS NULL"
            ),
            "expected_result": {"type": "zero_violations"},
            "explanation": (
                f"Counts rows in {table_name} where {column['name']} is missing, "
                "because the user explicitly requested a not-null check."
            ),
        }
    )
    return normalized_plan


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
    column, _score = _choose_column_with_score(text_prompt, table)
    return column


def _choose_column_with_score(text_prompt: str, table: dict[str, Any]) -> tuple[dict[str, Any], int]:
    columns = table.get("columns", [])
    if not columns:
        raise ValueError(f"No columns found for table {table.get('qualified_name') or table.get('table_name')}.")

    best_column = columns[0]
    best_score = 0
    match_text = _match_text(text_prompt)
    prompt_tokens = set(match_text.split())

    for column in columns:
        score = _column_match_score(match_text, prompt_tokens, str(column["name"]))
        if score > best_score:
            best_column = column
            best_score = score
    return best_column, best_score


def _column_match_score(match_text: str, prompt_tokens: set[str], column_name: str) -> int:
    variants = _column_variants(column_name)
    if any(f" {variant} " in f" {match_text} " for variant in variants):
        return 100

    column_tokens = [token for token in _match_text(column_name.replace("_", " ")).split() if len(token) >= 3]
    if column_tokens and all(token in prompt_tokens or f"{token}s" in prompt_tokens for token in column_tokens):
        return 80
    if any(token in prompt_tokens or f"{token}s" in prompt_tokens for token in column_tokens):
        return 40
    return 0


def _column_variants(column_name: str) -> set[str]:
    base = _match_text(column_name)
    spaced = _match_text(column_name.replace("_", " "))
    variants = {base, spaced}
    if not spaced.endswith("s"):
        variants.add(f"{spaced}s")
    if spaced.endswith("y"):
        variants.add(f"{spaced[:-1]}ies")
    return variants


def _match_text(value: str) -> str:
    value = value.lower().replace("'s", " ")
    value = re.sub(r"[^a-z0-9_]+", " ", value)
    value = value.replace("_", " ")
    return re.sub(r"\s+", " ", value).strip()


def _notification_channels_from_prompt(text_prompt: str) -> list[str]:
    match_text = _match_text(text_prompt)
    channels: list[str] = []
    if "slack" in match_text or "alert on slack" in text_prompt:
        channels.append("slack")
    if re.search(r"\b(?:email|e mail|mail|smtp)\b", match_text):
        channels.append("email")
    if not channels and "alert" in match_text:
        channels.append("slack")
    return list(dict.fromkeys(channels))


def _condition_from_prompt(
    text_prompt: str,
    column: dict[str, Any],
) -> tuple[str, int | float | str | tuple[int, int] | None]:
    null_phrases = [
        "not null",
        "never null",
        "never be null",
        "is never null",
        "should not be null",
        "must not be null",
        "cannot be null",
        "no null",
    ]
    if any(phrase in text_prompt for phrase in null_phrases):
        return "not_null", None
    future_phrases = [
        "in the future",
        "future date",
        "future-dated",
        "after today",
        "beyond today",
    ]
    if any(phrase in text_prompt for phrase in future_phrases):
        return "future_date", None
    if "negative" in text_prompt:
        return "<", 0

    between_values = _between_values(text_prompt)
    if between_values is not None:
        return ("inside_between" if _is_negative_constraint(text_prompt) else "outside_between"), between_values

    positive_requirement = _is_positive_requirement(text_prompt)
    if any(term in text_prompt for term in ["less than", "below", "under", "<"]):
        number = _number_after_terms(text_prompt, ["less than", "below", "under", "<"]) or _first_number(text_prompt) or 0
        return (">=" if positive_requirement else "<"), number
    if any(term in text_prompt for term in ["greater than", "above", "over", ">"]):
        number = _number_after_terms(text_prompt, ["greater than", "above", "over", ">"]) or _first_number(text_prompt) or 0
        return ("<=" if positive_requirement else ">"), number
    if any(term in text_prompt for term in ["equals", "equal to", "is "]):
        value = _equality_value(text_prompt)
        if positive_requirement and value not in {None, ""}:
            return "not_equals", value
        return "=", value if value is not None else ""
    column_names = {
        str(column["name"]).lower(),
        str(column["name"]).lower().replace("_", " "),
    }
    for column_name in column_names:
        escaped_column = re.escape(column_name)
        if re.search(rf"\b(?:has|have|having)\s+(?:a\s+|an\s+|the\s+)?{escaped_column}\b", text_prompt):
            return "not_null", None
        if re.search(rf"\b{escaped_column}\s+(?:exists|is present|is populated|has a value)\b", text_prompt):
            return "not_null", None
    return "<", _first_number(text_prompt) or 0


def _reject_prompt_injection(prompt: str) -> None:
    lowered = prompt.lower()
    if any(phrase in lowered for phrase in PROMPT_INJECTION_PHRASES):
        raise ValueError("Prompt appears to contain instruction-injection text. Rephrase it as a data quality rule only.")


def _normalize_prompt(text_prompt: str) -> str:
    replacements = {
        r"\bearns?\b": "salary",
        r"\bpay\b": "salary",
        r"\bpaid\b": "salary",
        r"\bcompensation\b": "salary",
        r"\bwage\b": "salary",
        r"\bsalry\b": "salary",
        r"\bsallary\b": "salary",
        r"\bjoined\b": "hired_at",
        r"\bjoining date\b": "hired_at",
        r"\bhire date\b": "hired_at",
        r"\bdate of hire\b": "hired_at",
        r"\bstart date\b": "hired_at",
        r"\bteam\b": "department",
        r"\bdept\b": "department",
        r"\bdivision\b": "department",
        r"\bemployee name\b": "full_name",
        r"\bname\b": "full_name",
        r"\bmarked as\b": "status is",
        r"\bemployment state\b": "status",
    }
    normalized = text_prompt
    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)
    return normalized


def _is_positive_requirement(text_prompt: str) -> bool:
    if _is_negative_constraint(text_prompt):
        return False
    return any(
        phrase in text_prompt
        for phrase in [
            "should be",
            "must be",
            "has to be",
            "needs to be",
            "need to be",
            "required to be",
            "is expected to be",
            "should have",
            "must have",
        ]
    )


def _is_negative_constraint(text_prompt: str) -> bool:
    return any(
        phrase in text_prompt
        for phrase in [
            "no ",
            "nobody",
            "none",
            "never",
            "should not",
            "must not",
            "cannot",
            "can't",
            "do not",
            "does not",
            "not be",
            "not have",
        ]
    )


def _between_values(text_prompt: str) -> tuple[int, int] | None:
    match = re.search(r"\bbetween\s+(\d+)\s+(?:and|to|-)\s+(\d+)\b", text_prompt)
    if match is None:
        return None
    first, second = int(match.group(1)), int(match.group(2))
    return (min(first, second), max(first, second))


def _number_after_terms(text_prompt: str, terms: list[str]) -> int | None:
    for term in terms:
        match = re.search(rf"{re.escape(term)}\s+(\d+)\b", text_prompt)
        if match:
            return int(match.group(1))
    return None


def _equality_value(text_prompt: str) -> int | str | None:
    quoted = re.search(r"['\"]([^'\"]+)['\"]", text_prompt)
    if quoted:
        return quoted.group(1)
    for pattern in [
        r"\bequal(?:s| to)?\s+([a-zA-Z_][a-zA-Z0-9_-]*)\b",
        r"\bis\s+([a-zA-Z_][a-zA-Z0-9_-]*)\b",
    ]:
        match = re.search(pattern, text_prompt)
        if match:
            value = match.group(1)
            if value not in {"not", "never", "null", "missing", "present", "populated"}:
                return value
    return _number_after_terms(text_prompt, ["equals", "equal to", "is"]) or _first_number(text_prompt)


def _schedule_text_from_prompt(text_prompt: str) -> str:
    match = re.search(
        r"\bevery\s+(?:(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+)?"
        r"(?:minute|minutes|hour|hours|day|days|week|weeks|month|months)"
        r"(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?",
        text_prompt,
    )
    if match:
        return match.group(0).strip()
    daily_match = re.search(r"\bdaily(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?", text_prompt)
    if daily_match:
        return daily_match.group(0).strip()
    for word in ("weekly", "monthly"):
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
    timeout_ms = get_settings().statement_timeout_ms
    try:
        async with target_engine(database_id) as engine:
            async with engine.connect() as conn:
                async with conn.begin():
                    await conn.execute(text("SET TRANSACTION READ ONLY"))
                    await conn.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
                    rows = (await conn.execute(text(f"SELECT * FROM ({sql}) AS plan_check LIMIT 2"))).mappings().all()
    except SQLAlchemyError as exc:
        raise ValueError(_friendly_dry_run_error(exc)) from exc
    if len(rows) != 1:
        raise SQLSafetyError("Generated SQL must return exactly one row.", "AI_RESULT_SHAPE")
    row = dict(rows[0])
    return {"row": row}


def _friendly_dry_run_error(exc: Exception) -> str:
    message = str(exc)
    lower_message = message.lower()
    if "undefinedcolumnerror" in lower_message or "column" in lower_message and "does not exist" in lower_message:
        return "Generated SQL references a column that does not exist in the selected database."
    if "invaliddatetimeformaterror" in lower_message or "invalid input syntax for type date" in lower_message:
        return "Generated SQL compared a date column to an invalid value. Try describing the date condition more explicitly."
    return "Generated SQL failed validation against the selected database. Check that referenced columns and value types are valid."


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
