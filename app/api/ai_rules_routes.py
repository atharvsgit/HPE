from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import logging

from app.daemon.registry import DuplicateRuleError
from app.services.ai_rules.orchestrator import generate_ai_rule, get_generation, approve_generation
from app.services.ai_rules.dry_run import dry_run_sql
from app.services.ai_rules.validator import SQLSafetyError, validate_ai_generated_sql
from app.services.ai_rules.sanitizer import PromptInjectionError
from app.services.ai_rules.export import export_learning_dataset
from app.services.ai_rules.scoring import update_rule_quality_scores
from app.services.ai_rules.improvement import generate_rule_improvement_suggestion
from app.services.ai_rules.correlation import find_similar_incidents

logger = logging.getLogger(__name__)

ai_rules_router = APIRouter(prefix="/ai-rules", tags=["ai-rules"])

class GenerateRequest(BaseModel):
    prompt: str
    schema_name: str
    table_name: str

class DryRunRequest(BaseModel):
    sql: str

class SaveRequest(BaseModel):
    generation_id: int
    reviewed_sql: str

@ai_rules_router.post("/generate")
async def generate_rule(req: GenerateRequest):
    try:
        result = await generate_ai_rule(req.prompt, req.schema_name, req.table_name)
        return result
    except PromptInjectionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLSafetyError as e:
        # Generated SQL was unsafe
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Generate error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during rule generation.")

@ai_rules_router.post("/dry-run")
async def dry_run_rule(req: DryRunRequest):
    try:
        validate_ai_generated_sql(req.sql)
        result = await dry_run_sql(req.sql)
        return result
    except SQLSafetyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ai_rules_router.post("/save")
async def save_rule(req: SaveRequest):
    try:
        # approver could come from auth token if auth is implemented
        approver = "user" 
        result = await approve_generation(req.generation_id, req.reviewed_sql, approver)
        return {"status": "success", "data": result}
    except SQLSafetyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except DuplicateRuleError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "type": "DUPLICATE_RULE",
                "message": str(e),
                "existing_rule_id": e.existing_rule_id,
            },
        )
    except Exception as e:
        logger.error(f"Save error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@ai_rules_router.get("/history/{generation_id}")
async def get_rule_history(generation_id: int):
    try:
        result = await get_generation(generation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@ai_rules_router.get("/export", response_class=PlainTextResponse)
async def export_dataset():
    try:
        jsonl_io = await export_learning_dataset()
        return jsonl_io.getvalue()
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(status_code=500, detail="Failed to export dataset")

@ai_rules_router.post("/score-rules")
async def trigger_scoring(background_tasks: BackgroundTasks):
    background_tasks.add_task(update_rule_quality_scores)
    return {"status": "accepted", "message": "Scoring job started in the background."}

@ai_rules_router.get("/suggestions/{rule_id}")
async def get_rule_suggestion(rule_id: int):
    try:
        suggestion = await generate_rule_improvement_suggestion(rule_id)
        return suggestion
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get suggestion for rule {rule_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate suggestion")

class SuggestionStatusUpdate(BaseModel):
    status: str # 'accepted', 'rejected'

@ai_rules_router.post("/suggestions/{suggestion_id}/status")
async def update_suggestion_status(suggestion_id: int, payload: SuggestionStatusUpdate):
    try:
        from app.db.session import metadata_engine
        from sqlalchemy import text
        async with metadata_engine.begin() as conn:
            await conn.execute(
                text("UPDATE dq_results.rule_improvement_suggestions SET status = :status, updated_at = NOW() WHERE id = :id"),
                {"status": payload.status, "id": suggestion_id}
            )
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to update suggestion {suggestion_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update suggestion status")

@ai_rules_router.get("/correlations/{batch_id}")
async def get_correlations(batch_id: int, threshold: float = 0.3):
    try:
        correlations = await find_similar_incidents(batch_id, threshold)
        if not correlations:
            return {"message": "No meaningful historical correlations found.", "correlations": []}
        return {"correlations": correlations}
    except Exception as e:
        logger.error(f"Failed to fetch correlations for batch {batch_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch correlations")

