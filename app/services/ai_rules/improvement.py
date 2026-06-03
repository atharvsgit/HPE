import json
import logging
from sqlalchemy import text
from app.db.session import metadata_engine
from app.services.llm.providers.groq_provider import GroqProvider
from app.services.llm.parser import parse_and_validate

logger = logging.getLogger(__name__)

SUGGESTION_PROMPT_TEMPLATE = """
You are an expert Data Quality Rule Optimizer. Your task is to analyze historical operational metrics and human feedback to suggest ONE narrow, evidence-backed improvement for a data quality rule.

Do NOT generate entirely new rules or destructive rewrites.
Supported Suggestion Types:
- threshold_tuning
- null_handling
- filter_refinement
- scheduler_cadence
- join_correction
- stale_rule_detection

Rule Details:
Name: {rule_name}
Current SQL: 
{sql_text}

Evidence:
- Total Executions (30d): {executions}
- Total Failures (30d): {failures}
- False Positive Rate (Est): {fp_rate}%
- Reviewer Rejections: {rejections}
- Recent Human Corrections (if any):
{human_corrections}

Output exactly valid JSON matching this schema:
{{
  "suggestion_type": "string (one of the supported types)",
  "current_behavior": "Briefly describe current behavior",
  "recommended_change": "Brief description of the change. If SQL, provide the updated snippet.",
  "reasoning": "Why this improves signal quality/operator trust",
  "supporting_evidence": ["Evidence point 1", "Evidence point 2"],
  "confidence": "high|medium|low",
  "risk_level": "low|medium|high"
}}

If there is insufficient evidence to make a confident recommendation (e.g., low failure rate, no rejections), return:
{{
  "suggestion_type": "none",
  "current_behavior": "Operating normally",
  "recommended_change": "No change needed",
  "reasoning": "Insufficient historical evidence to justify modification",
  "supporting_evidence": [],
  "confidence": "low",
  "risk_level": "low"
}}
"""

async def _gather_evidence(rule_id: int) -> dict:
    async with metadata_engine.connect() as conn:
        rule_res = await conn.execute(
            text("SELECT rule_name, sql_text, false_positive_rate FROM dq_config.dq_rules WHERE rule_id = :rule_id"),
            {"rule_id": rule_id}
        )
        rule = rule_res.mappings().first()
        if not rule:
            return None

        # Executions & Failures
        exec_res = await conn.execute(
            text("SELECT COUNT(*) FROM dq_results.test_results WHERE rule_id = :rule_id AND executed_at > NOW() - INTERVAL '30 days'"),
            {"rule_id": rule_id}
        )
        executions = exec_res.scalar_one() or 0

        fail_res = await conn.execute(
            text("SELECT COUNT(*) FROM dq_results.test_results WHERE rule_id = :rule_id AND status = 'FAIL' AND executed_at > NOW() - INTERVAL '30 days'"),
            {"rule_id": rule_id}
        )
        failures = fail_res.scalar_one() or 0

        # Rejections & Edits
        fb_res = await conn.execute(
            text("""
                SELECT f.feedback_type, f.edited_summary, f.created_at
                FROM dq_results.llm_feedback f
                JOIN dq_results.violation_batches b ON b.id = f.violation_batch_id
                WHERE b.rule_id = :rule_id AND f.created_at > NOW() - INTERVAL '30 days'
                ORDER BY f.created_at DESC
                LIMIT 5
            """),
            {"rule_id": rule_id}
        )
        feedback_rows = fb_res.mappings().all()

    rejections = sum(1 for fb in feedback_rows if fb["feedback_type"] == "reject")
    edits = [fb["edited_summary"] for fb in feedback_rows if fb["feedback_type"] in ("edit", "annotate") and fb["edited_summary"]]

    human_corrections_text = "\n".join(f"- {e}" for e in edits) if edits else "None recorded."

    return {
        "rule_name": rule["rule_name"],
        "sql_text": rule["sql_text"],
        "fp_rate": rule["false_positive_rate"],
        "executions": executions,
        "failures": failures,
        "rejections": rejections,
        "human_corrections": human_corrections_text
    }

async def generate_rule_improvement_suggestion(rule_id: int) -> dict:
    evidence = await _gather_evidence(rule_id)
    if not evidence:
        raise ValueError(f"Rule {rule_id} not found.")

    # If evidence is too weak, short-circuit
    if evidence["failures"] < 5 and evidence["rejections"] == 0 and evidence["fp_rate"] < 5.0:
        return {
            "suggestion_type": "none",
            "message": "No reliable recommendation available. (Insufficient historical evidence)"
        }

    provider = GroqProvider()
    prompt = SUGGESTION_PROMPT_TEMPLATE.format(**evidence)
    
    try:
        raw_json = await provider.generate_json(prompt, "You are a conservative, evidence-driven Data Quality assistant. Output only JSON.")
        
        # Simple schema validation fallback
        if "suggestion_type" not in raw_json or raw_json["suggestion_type"] == "none":
             return {
                 "suggestion_type": "none",
                 "message": "No reliable recommendation available."
             }
             
        # Insert into DB
        async with metadata_engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO dq_results.rule_improvement_suggestions
                    (rule_id, suggestion_type, suggested_sql, reasoning, status)
                    VALUES (:rule_id, :stype, :sql, :reasoning, 'pending')
                """),
                {
                    "rule_id": rule_id,
                    "stype": raw_json["suggestion_type"],
                    "sql": raw_json.get("recommended_change", ""),
                    "reasoning": json.dumps({
                        "reasoning": raw_json.get("reasoning"),
                        "evidence": raw_json.get("supporting_evidence"),
                        "confidence": raw_json.get("confidence"),
                        "risk": raw_json.get("risk_level")
                    })
                }
            )
            
        return raw_json
        
    except Exception as e:
        logger.error(f"Failed to generate rule improvement: {e}")
        return {
            "suggestion_type": "error",
            "message": "Failed to generate recommendation due to an internal error."
        }
