"""
app/platform/rule_intelligence/gemini_engine.py
-------------------------------------------------
Generates data quality rule suggestions using Google Gemini 2.5 Flash
via the optional ``google-genai`` SDK.

The engine sends a structured prompt containing the dataset profile to
Gemini and expects a JSON array of rule suggestion objects back.

Switch between heuristic and Gemini engines via the
``RULE_SUGGESTION_BACKEND`` environment variable or per-request via the
``backend`` field in :class:`~app.models.platform_requests.RuleSuggestionRequest`.
"""
from __future__ import annotations

import json
import re

from app.platform.logger import get_logger
from app.settings import get_settings

log = get_logger(__name__)


class GeminiEngineError(Exception):
    """Raised when the Gemini API call fails or returns unparseable output."""


async def suggest_rules_gemini(profile: dict, table_name: str) -> list[dict]:
    """
    Call Gemini 2.5 Flash with a structured prompt derived from *profile*
    and return a list of rule suggestion dicts.

    Args:
        profile:    Profile dict from :func:`~app.platform.profiling.profiler.profile_table`.
        table_name: Fully-qualified table name used in SQL generation.

    Returns:
        List of suggestion dicts in the same shape as :func:`heuristic_engine.suggest_rules`.

    Raises:
        GeminiEngineError: If no API key is configured, the API call fails,
                           or the response cannot be parsed as JSON.
    """
    settings = get_settings()

    if not settings.gemini_api_key:
        raise GeminiEngineError(
            "GEMINI_API_KEY is not set. "
            "Either configure the key or use backend='heuristic'."
        )

    # Import here so the module can be imported even without google-genai installed
    # (the dependency is optional at import time; missing at runtime raises clearly).
    try:
        from google import genai  # type: ignore[import-untyped]
    except ImportError as exc:
        raise GeminiEngineError(
            "google-genai is not installed in this prototype image. "
            "Add it to requirements.txt before using backend='gemini'."
        ) from exc

    prompt = _build_prompt(profile, table_name)
    log.info("Calling Gemini API for rule suggestions on '{t}'.", t=table_name)

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        raw_text: str = response.text
    except Exception as exc:
        raise GeminiEngineError(f"Gemini API call failed: {exc}") from exc

    suggestions = _parse_response(raw_text, table_name)
    log.info(
        "Gemini returned {n} suggestions for '{t}'.",
        n=len(suggestions),
        t=table_name,
    )
    return suggestions


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt(profile: dict, table_name: str) -> str:
    """
    Build the structured prompt sent to Gemini.

    The prompt provides the profile summary and asks for a specific JSON format
    so the response can be reliably parsed.
    """
    profile_summary = json.dumps(
        {
            "table_name": table_name,
            "row_count": profile.get("row_count"),
            "column_count": profile.get("column_count"),
            "null_summary": profile.get("null_summary"),
            "schema_info": profile.get("schema_info"),
            "statistics": profile.get("statistics"),
            "uniqueness": profile.get("uniqueness"),
        },
        indent=2,
        default=str,
    )

    return f"""You are a data quality expert. Given the following dataset profile,
generate SQL-based data quality validation rules for a PostgreSQL database.

Dataset profile:
{profile_summary}

Return a JSON array of rule suggestions. Each element must be a JSON object
with EXACTLY these fields (no extras):
{{
  "column_name": "<column name or '__dataset__' for table-level rules>",
  "suggested_rule_name": "<short human-readable rule name>",
  "suggested_sql": "<single SELECT SQL returning exactly one row with one column named violation_count or observed_value>",
  "expected_result_type": "<one of: zero_violations | min_threshold | max_threshold | equals>",
  "expected_result_value": <numeric value or null>,
  "confidence": <float 0.0 to 1.0>
}}

Important constraints for the SQL:
- Table name must be: {table_name}
- SQL must be a single SELECT statement
- Must return exactly one numeric column named either violation_count or observed_value
- Do not use semicolons at the end
- Do not use CTEs or subqueries that reference unavailable tables
- Use only standard PostgreSQL syntax

Generate between 3 and 10 high-quality rules. Return ONLY the JSON array,
no explanation text before or after it.
"""


def _parse_response(raw_text: str, table_name: str) -> list[dict]:
    """
    Extract and parse the JSON array from Gemini's response text.

    Gemini sometimes wraps the JSON in markdown code fences; this function
    strips those before parsing.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_text).strip()
    cleaned = cleaned.rstrip("`").strip()

    # Find the outermost JSON array
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1:
        raise GeminiEngineError(
            f"Gemini response did not contain a JSON array. Raw: {raw_text[:500]}"
        )

    try:
        parsed: list[dict] = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GeminiEngineError(
            f"Failed to parse Gemini JSON response: {exc}. Raw: {raw_text[:500]}"
        ) from exc

    results: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        results.append({
            "column_name": str(item.get("column_name", "__dataset__")),
            "table_name": table_name,
            "suggestion_type": "gemini",
            "suggested_rule_name": str(item.get("suggested_rule_name", "Unnamed rule")),
            "suggested_sql": str(item.get("suggested_sql", "")),
            "expected_result_type": str(item.get("expected_result_type", "zero_violations")),
            "expected_result_value": _safe_float(item.get("expected_result_value")),
            "confidence": _safe_float(item.get("confidence")) or 0.5,
        })

    return results


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
