from fastapi import APIRouter, HTTPException, status

from app.llm import drafts
from app.llm.models import LLMDraftRequest, LLMDraftResponse, LLMDraftReviewRequest
from app.llm.provider import get_llm_provider
from app.llm.validator import validate_candidate

router = APIRouter(prefix="/llm/rules", tags=["LLM Drafts"])


@router.post("/draft", response_model=LLMDraftResponse, status_code=status.HTTP_201_CREATED)
async def create_llm_draft(request: LLMDraftRequest):
    provider = get_llm_provider()
    
    # In a real scenario we might wrap this in a try-except to catch 
    # LLM failures and wrap them into a nice 500 error, but this works for MVP
    candidate = await provider.generate_draft(request.prompt)
    if request.schedule_cron:
        candidate.schedule_cron = request.schedule_cron
    
    val_status, errors, dry_run_res = await validate_candidate(candidate, request.dry_run)
    
    return await drafts.create_draft(
        intent=request.prompt,
        candidate=candidate,
        validation_status=val_status,
        validation_errors=errors,
        dry_run_res=dry_run_res
    )


@router.get("/drafts", response_model=list[LLMDraftResponse])
async def list_drafts():
    return await drafts.list_drafts()


@router.get("/drafts/{draft_id}", response_model=LLMDraftResponse)
async def get_draft(draft_id: int):
    draft = await drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/drafts/{draft_id}/approve", response_model=LLMDraftResponse)
async def approve_draft(draft_id: int):
    try:
        return await drafts.approve_draft(draft_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/drafts/{draft_id}/reject", response_model=LLMDraftResponse)
async def reject_draft(draft_id: int, review: LLMDraftReviewRequest):
    try:
        return await drafts.update_reviewer_status(draft_id, "rejected", review.reviewer_notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/drafts/{draft_id}/request-changes", response_model=LLMDraftResponse)
async def request_changes(draft_id: int, review: LLMDraftReviewRequest):
    try:
        return await drafts.update_reviewer_status(draft_id, "changes_requested", review.reviewer_notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
