import logging
import json
import re
from sqlalchemy import text
from app.daemon.registry import DuplicateRuleError, create_rule
from app.db.session import metadata_engine
from app.models.requests import ExpectedResult, SavedRuleCreateRequest
from app.services.ai_rules.sanitizer import sanitize_prompt
from app.services.ai_rules.schema_context import get_schema_context
from app.services.ai_rules.prompts import SYSTEM_PROMPT
from app.services.ai_rules.parser import parse_llm_response, AIRuleResponse
from app.services.ai_rules.validator import validate_ai_generated_sql
from app.services.llm.providers.groq_provider import GroqProvider
from app.settings import get_settings
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def generate_ai_rule(
    prompt: str,
    schema_name: str,
    table_name: str,
) -> Dict[str, Any]:
    """
    Coordinates the generation pipeline:
    1. Sanitize prompt
    2. Inject schema context
    3. Generate SQL using LLM
    4. Parse and Validate
    5. Save draft in DB
    """
    # 1. Sanitize Prompt
    clean_prompt = sanitize_prompt(prompt)

    # 2. Get Schema Context
    schema_context = await get_schema_context(schema_name, table_name)
    
    # 3. Get existing rules for few-shot examples
    existing_rules_str = await _get_existing_rules(schema_name, table_name)
    
    # 4. Generate SQL
    sys_prompt = SYSTEM_PROMPT.format(
        schema_context=schema_context,
        dynamic_examples=existing_rules_str
    )
    
    settings = get_settings()
    provider_name = "Groq"
    model_name = settings.llm_model

    if settings.groq_api_key:
        try:
            llm_payload = await GroqProvider().generate_json(clean_prompt, sys_prompt)
            llm_text = json.dumps(llm_payload)
        except Exception as e:
            logger.error(f"LLM Generation failed: {e}")
            raise RuntimeError("Failed to generate rule with AI.")
    else:
        table_ref = _qualified_table(schema_name, table_name)
        llm_text = json.dumps({
            "sql": f"SELECT COUNT(*) AS violation_count FROM {table_ref} WHERE FALSE;",
            "explanation": "No Groq API key is configured, so a safe draft was generated for human editing.",
            "assumptions": ["A human reviewer will replace the placeholder condition before approval."],
            "possible_edge_cases": ["The placeholder condition never returns violations."],
            "confidence_reasoning": "Fallback draft only; it is syntactically safe but not semantically useful.",
            "confidence": "low",
        })
        provider_name = "Fallback"
        model_name = "local-safe-draft"
        
    # 5. Parse and Validate
    try:
        parsed: AIRuleResponse = parse_llm_response(llm_text)
        validate_ai_generated_sql(parsed.sql)
    except Exception as e:
        logger.error(f"Parsing/Validation failed: {e}")
        # Even if it fails validation, we log it for audit
        generation_id = await _log_generation(
            clean_prompt, prompt, None, str(e), None, None, None,
            provider_name, model_name, True
        )
        raise ValueError(f"AI generation failed validation: {e}")

    # 6. Log success draft in DB
    generation_id = await _log_generation(
        clean_prompt,
        prompt,
        parsed.sql,
        parsed.explanation,
        parsed.assumptions,
        parsed.possible_edge_cases,
        parsed.confidence,
        provider_name,
        model_name,
        False
    )
    
    return {
        "id": generation_id,
        "sql": parsed.sql,
        "explanation": parsed.explanation,
        "assumptions": parsed.assumptions,
        "possible_edge_cases": parsed.possible_edge_cases,
        "confidence_reasoning": parsed.confidence_reasoning,
        "confidence": parsed.confidence
    }

async def _get_existing_rules(schema_name: str, table_name: str) -> str:
    """Fetch a few existing approved rules to use as dynamic examples."""
    try:
        async with metadata_engine.connect() as conn:
            res = await conn.execute(
                text(
                    """
                    SELECT rule_name, sql_text
                    FROM dq_config.dq_rules
                    WHERE is_enabled = true
                      AND sql_text ILIKE :table_pattern
                    LIMIT 3
                    """
                ),
                {"table_pattern": f"%{schema_name}.{table_name}%"},
            )
            rules = res.mappings().all()
            if not rules:
                return "No existing rules found."
                
            formatted = []
            for i, r in enumerate(rules, 1):
                formatted.append(
                    f"Example {i}:\nUser: {r['rule_name']}\nResponse:\n{{\"sql\": \"{r['sql_text']}\"}}"
                )
            return "\n\n".join(formatted)
    except Exception as e:
        logger.warning(f"Failed to fetch existing rules: {e}")
        return ""

async def _log_generation(
    clean_prompt: str,
    original_prompt: str,
    generated_sql: str | None,
    explanation: str | None,
    assumptions: list | None,
    possible_edge_cases: list | None,
    confidence: str | None,
    provider_name: str,
    model_name: str,
    parsing_failure: bool
) -> int:
    """Log generation attempt to db."""
    async with metadata_engine.connect() as conn:
        async with conn.begin():
            res = await conn.execute(
                text(
                    """
                    INSERT INTO dq_results.ai_rule_generations (
                        prompt, original_prompt, generated_sql, explanation,
                        assumptions, possible_edge_cases, confidence,
                        provider_name, model_name, prompt_version,
                        parsing_failure
                    ) VALUES (
                        :prompt, :original_prompt, :generated_sql, :explanation,
                        :assumptions, :possible_edge_cases, :confidence,
                        :provider_name, :model_name, 'v1',
                        :parsing_failure
                    ) RETURNING id
                    """
                ),
                {
                    "prompt": clean_prompt,
                    "original_prompt": original_prompt,
                    "generated_sql": generated_sql,
                    "explanation": explanation,
                    "assumptions": json.dumps(assumptions) if assumptions else None,
                    "possible_edge_cases": json.dumps(possible_edge_cases) if possible_edge_cases else None,
                    "confidence": confidence,
                    "provider_name": provider_name,
                    "model_name": model_name,
                    "parsing_failure": parsing_failure,
                }
            )
            return res.scalar_one()

async def get_generation(generation_id: int) -> Dict[str, Any]:
    async with metadata_engine.connect() as conn:
        res = await conn.execute(
            text("SELECT * FROM dq_results.ai_rule_generations WHERE id = :id"),
            {"id": generation_id}
        )
        row = res.mappings().first()
        if not row:
            raise ValueError(f"Generation {generation_id} not found.")
        return dict(row)

async def approve_generation(generation_id: int, sql: str, approver: str = "system") -> Dict[str, Any]:
    """Approve a generation, save edits, and create a saved rule."""
    # Validate the final SQL just in case
    validate_ai_generated_sql(sql)

    async with metadata_engine.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT generated_sql, approved, saved_rule_id
                FROM dq_results.ai_rule_generations
                WHERE id = :id
                """
            ),
            {"id": generation_id},
        )
        row = res.mappings().first()
    if not row:
        raise ValueError("Generation not found.")
    if row["approved"]:
        raise DuplicateRuleError(row["saved_rule_id"], f"AI approved rule {generation_id}")

    edited = row["generated_sql"] != sql
    saved_rule = await create_rule(
        SavedRuleCreateRequest(
            rule_name=f"AI approved rule {generation_id}",
            sql=sql,
            expected_result=ExpectedResult(type="zero_violations"),
            notification_channels=["slack"],
            severity="medium",
        )
    )

    async with metadata_engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text(
                    """
                    UPDATE dq_results.ai_rule_generations
                    SET approved = true,
                        approved_by = :approver,
                        approval_timestamp = NOW(),
                        reviewed_sql = :sql,
                        edited_after_generation = :edited,
                        saved_rule_id = :saved_rule_id
                    WHERE id = :id
                    """
                ),
                {
                    "id": generation_id,
                    "approver": approver,
                    "sql": sql,
                    "edited": edited,
                    "saved_rule_id": saved_rule.rule_id,
                },
            )

            res2 = await conn.execute(
                text("SELECT * FROM dq_results.ai_rule_generations WHERE id = :id"),
                {"id": generation_id},
            )
            approved_row = dict(res2.mappings().first())
            approved_row["saved_rule_id"] = saved_rule.rule_id
            return approved_row


def _qualified_table(schema_name: str, table_name: str) -> str:
    return ".".join(_quote_identifier(part) for part in (_safe_identifier(schema_name), _safe_identifier(table_name)))


def _safe_identifier(value: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        raise ValueError("Schema and table names must be simple PostgreSQL identifiers.")
    return value


def _quote_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) * 2)}"'
