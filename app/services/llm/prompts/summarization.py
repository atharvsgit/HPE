"""
LLM prompt templates for violation batch summarization.
Kept separate from provider and worker logic to allow independent iteration.
"""
from app.services.llm.sanitizer import default_sanitizer

PROMPT_VERSION = "v1.1.0"

SYSTEM_PROMPT = """\
You are a data quality analyst assistant. Your job is to analyze data quality violations \
and produce a concise, structured report for engineering and business teams.

You MUST respond ONLY with a valid JSON object matching this exact schema — no extra text, \
no markdown, no explanation:

{
  "summary": "<one-paragraph executive summary, 2-3 sentences max>",
  "root_causes": ["<cause 1>", "<cause 2>"],
  "suggested_fixes": ["<fix 1>", "<fix 2>"],
  "business_impact": "<brief business impact statement>",
  "confidence": "<high|medium|low>"
}

Rules:
- summary: concise, factual, non-technical where possible.
- root_causes: list of 1-4 plausible technical root causes.
- suggested_fixes: list of 1-4 actionable fix suggestions (SQL, pipeline, schema changes).
- business_impact: one sentence describing downstream risk to data consumers.
- confidence: string indicating your confidence level (high, medium, low).
- Do NOT reference internal system names.
- Do NOT mention that you are an AI.
"""


def build_summarization_prompt(
    rule_name: str,
    rule_description: str | None,
    severity: str,
    violation_count: int | float | None,
    sample_rows: list[dict] | None,
    trend_summary: str | None,
) -> str:
    """
    Builds the user-turn prompt for violation summarization.
    Applies token safety measures: truncates sample rows and sanitizes values via DataSanitizer.
    """
    # Cap sample rows to prevent token bloat
    MAX_SAMPLE_ROWS = 5
    safe_samples = (sample_rows or [])[:MAX_SAMPLE_ROWS]

    lines = [
        f"Rule Name: {rule_name}",
        f"Severity: {severity}",
        f"Violation Count: {violation_count if violation_count is not None else 'unknown'}",
    ]
    if rule_description:
        lines.append(f"Rule Description: {rule_description[:500]}")

    if safe_samples:
        lines.append(f"Sample Violating Rows (up to {MAX_SAMPLE_ROWS}):")
        for i, row in enumerate(safe_samples, 1):
            sanitized_row = default_sanitizer.sanitize_row(row)
            lines.append(f"  Row {i}: {sanitized_row}")

    if trend_summary:
        lines.append(f"Recent Trend: {trend_summary[:300]}")

    return "\n".join(lines)
