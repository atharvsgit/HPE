import json
import io
import re
from sqlalchemy import text
from app.db.session import metadata_engine

def sanitize_jsonl_value(val):
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    # Remove obvious PII patterns loosely (very basic for example purposes)
    s = str(val)
    s = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]', s)
    s = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]', s)
    return s

async def export_learning_dataset() -> io.StringIO:
    """
    Exports a sanitized, structured JSONL dataset of AI Rule Generations
    merged with final approved rules. Excludes raw sample rows.
    """
    output = io.StringIO()
    
    async with metadata_engine.connect() as conn:
        res = await conn.execute(
            text("""
                SELECT 
                    a.id, 
                    a.prompt, 
                    a.original_prompt,
                    a.generated_sql, 
                    a.explanation, 
                    a.confidence,
                    a.model_name,
                    a.prompt_version,
                    a.reviewed_sql,
                    a.edited_after_generation,
                    a.approved_by,
                    a.parsing_failure
                FROM dq_results.ai_rule_generations a
                WHERE a.approved = true
                ORDER BY a.created_at ASC
            """)
        )
        
        rows = res.mappings().all()
        
        for row in rows:
            # Construct a structured JSON object
            data = {
                "id": f"gen_{row['id']}",
                "prompt": sanitize_jsonl_value(row["prompt"]),
                "generated_sql": sanitize_jsonl_value(row["generated_sql"]),
                "reviewed_sql": sanitize_jsonl_value(row["reviewed_sql"]),
                "edited_after_generation": row["edited_after_generation"],
                "metadata": {
                    "confidence": row["confidence"],
                    "model_name": row["model_name"],
                    "prompt_version": row["prompt_version"],
                    "parsing_failure": row["parsing_failure"],
                }
            }
            # Write as JSONL
            output.write(json.dumps(data) + "\n")
            
    output.seek(0)
    return output
