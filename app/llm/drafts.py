import json

from sqlalchemy import text

from app.daemon.registry import create_rule
from app.db.session import metadata_engine as db_engine
from app.llm.models import (
    LLMDraftDryRunResult,
    LLMDraftResponse,
    LLMRuleCandidate,
)
from app.models.requests import ExpectedResult, SavedRuleCreateRequest


async def create_draft(
    intent: str,
    candidate: LLMRuleCandidate,
    validation_status: str,
    validation_errors: list[str],
    dry_run_res: LLMDraftDryRunResult | None,
) -> LLMDraftResponse:
    dry_run_status = None
    dry_run_observed_key = None
    dry_run_observed_value = None
    dry_run_error_message = None

    if dry_run_res:
        dry_run_status = dry_run_res.status
        dry_run_observed_key = dry_run_res.observed_key
        dry_run_observed_value = dry_run_res.observed_value
        dry_run_error_message = dry_run_res.error_message

    async with db_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                INSERT INTO dq_config.llm_rule_drafts (
                    source_prompt,
                    rule_name,
                    sql_text,
                    expected_result_type,
                    expected_result_value,
                    schedule_cron,
                    validation_status,
                    validation_errors,
                    dry_run_status,
                    dry_run_observed_key,
                    dry_run_observed_value,
                    dry_run_error_message
                ) VALUES (
                    :source_prompt,
                    :rule_name,
                    :sql_text,
                    :expected_result_type,
                    :expected_result_value,
                    :schedule_cron,
                    :validation_status,
                    :validation_errors,
                    :dry_run_status,
                    :dry_run_observed_key,
                    :dry_run_observed_value,
                    :dry_run_error_message
                ) RETURNING *
                """
            ),
            {
                "source_prompt": intent,
                "rule_name": candidate.rule_name,
                "sql_text": candidate.sql,
                "expected_result_type": candidate.expected_result.type,
                "expected_result_value": candidate.expected_result.value,
                "schedule_cron": candidate.schedule_cron,
                "validation_status": validation_status,
                "validation_errors": json.dumps(validation_errors),
                "dry_run_status": dry_run_status,
                "dry_run_observed_key": dry_run_observed_key,
                "dry_run_observed_value": dry_run_observed_value,
                "dry_run_error_message": dry_run_error_message,
            },
        )
        row = result.mappings().one()
        return _draft_from_row(row)


async def get_draft(draft_id: int) -> LLMDraftResponse | None:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT * FROM dq_config.llm_rule_drafts WHERE draft_id = :draft_id"),
            {"draft_id": draft_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return _draft_from_row(row)


async def list_drafts() -> list[LLMDraftResponse]:
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT * FROM dq_config.llm_rule_drafts ORDER BY created_at DESC")
        )
        return [_draft_from_row(row) for row in result.mappings().all()]


async def approve_draft(draft_id: int) -> LLMDraftResponse:
    draft = await get_draft(draft_id)
    if not draft:
        raise ValueError("Draft not found")
    if draft.reviewer_status == "approved":
        raise ValueError("Draft is already approved")
    if draft.validation_status != "valid":
        raise ValueError("Cannot approve an invalid draft")

    req = SavedRuleCreateRequest(
        rule_name=draft.rule_name,
        sql=draft.sql,
        expected_result=draft.expected_result,
        schedule_cron=draft.schedule_cron,
        is_enabled=True,
    )
    
    saved_rule = await create_rule(req)

    async with db_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE dq_config.llm_rule_drafts
                SET reviewer_status = 'approved',
                    approved_rule_id = :approved_rule_id,
                    updated_at = NOW()
                WHERE draft_id = :draft_id
                RETURNING *
                """
            ),
            {"draft_id": draft_id, "approved_rule_id": saved_rule.rule_id},
        )
        row = result.mappings().one()
        return _draft_from_row(row)


async def update_reviewer_status(draft_id: int, status: str, notes: str | None = None) -> LLMDraftResponse:
    async with db_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                UPDATE dq_config.llm_rule_drafts
                SET reviewer_status = :status,
                    reviewer_notes = :notes,
                    updated_at = NOW()
                WHERE draft_id = :draft_id
                RETURNING *
                """
            ),
            {"draft_id": draft_id, "status": status, "notes": notes},
        )
        row = result.mappings().first()
        if not row:
            raise ValueError("Draft not found")
        return _draft_from_row(row)


def _draft_from_row(row) -> LLMDraftResponse:
    dry_run_res = None
    if row["dry_run_status"]:
        dry_run_res = LLMDraftDryRunResult(
            status=row["dry_run_status"],
            observed_key=row["dry_run_observed_key"],
            observed_value=float(row["dry_run_observed_value"]) if row["dry_run_observed_value"] is not None else None,
            error_message=row["dry_run_error_message"],
        )
    
    expected_result = None
    if row["expected_result_type"]:
        expected_result = ExpectedResult(
            type=row["expected_result_type"],
            value=row["expected_result_value"]
        )

    return LLMDraftResponse(
        draft_id=row["draft_id"],
        source_prompt=row["source_prompt"],
        rule_name=row["rule_name"],
        sql=row["sql_text"],
        expected_result=expected_result,
        schedule_cron=row["schedule_cron"],
        validation_status=row["validation_status"],
        validation_errors=row["validation_errors"] if isinstance(row["validation_errors"], list) else json.loads(row["validation_errors"]),
        dry_run=dry_run_res,
        reviewer_status=row["reviewer_status"],
        reviewer_notes=row["reviewer_notes"],
        approved_rule_id=row["approved_rule_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
