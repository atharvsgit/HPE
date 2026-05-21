import time
from sqlalchemy import text
from app.db.session import executor_engine
import json
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

async def dry_run_sql(sql: str, timeout_ms: int = 5000, max_rows: int = 10) -> Dict[str, Any]:
    """
    Safely execute the generated SQL using the restricted executor role.
    Enforces transaction rollback, timeouts, and limits output rows.
    """
    start_time = time.time()
    
    # We enforce LIMIT implicitly by wrapping if it's a raw SELECT
    # For a count query (as expected), limit isn't strictly necessary for rows,
    # but the requirement states: "enforce LIMIT automatically if missing", "cap returned preview rows".
    # Since the AI should generate a COUNT(*), we just run it as is, but we also 
    # want to run a sample data query to show violating rows. Wait, if it generates count, it just returns a number.
    # To get violating rows, we'd need to strip the aggregation. But the AI is generating the aggregate query.
    # We will just run the user's query with a LIMIT just in case it returns multiple rows unexpectedly.
    
    # Simple limit enforcement: if it doesn't contain limit, append LIMIT (this is naive, but works for simple cases, and it's wrapped in a subquery just in case).
    limited_sql = f"SELECT * FROM ({sql}) AS dry_run_subquery LIMIT {max_rows}"

    success = False
    result_data = None
    error_msg = None
    estimated_cost = None
    
    try:
        async with executor_engine.connect() as conn:
            async with conn.begin() as trans:
                # Force read-only and local timeout
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                await conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                
                # Optionally run EXPLAIN to get estimated cost
                try:
                    explain_res = await conn.execute(text(f"EXPLAIN {sql}"))
                    explain_lines = explain_res.fetchall()
                    if explain_lines:
                        # Extract cost from first line: e.g., "Aggregate  (cost=12.34..12.35 rows=1 width=8)"
                        estimated_cost = explain_lines[0][0]
                except Exception as e:
                    logger.warning(f"Dry run EXPLAIN failed: {e}")

                # Execute actual query
                result = await conn.execute(text(limited_sql))
                rows = result.mappings().all()
                result_data = [dict(row) for row in rows]
                success = True
                
                # Explicitly rollback to guarantee no state changes
                await trans.rollback()
    except Exception as e:
        success = False
        error_msg = str(e)
        logger.error(f"Dry run execution failed: {e}")
        
    latency_ms = int((time.time() - start_time) * 1000)
    
    return {
        "success": success,
        "latency_ms": latency_ms,
        "estimated_cost": estimated_cost,
        "sample_output": result_data,
        "error": error_msg
    }
