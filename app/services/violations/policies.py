import logging
from datetime import datetime

from sqlalchemy import text

from app.db.session import metadata_engine as db_engine
from app.models.violations import NotificationPolicy

logger = logging.getLogger(__name__)


async def get_or_create_policy(rule_id: int) -> NotificationPolicy:
    async with db_engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT
                    id,
                    rule_id,
                    immediate_threshold,
                    batch_window_minutes,
                    deduplication_window_minutes,
                    enable_llm_summary,
                    enable_fix_suggestions,
                    slack_enabled,
                    email_enabled,
                    created_at
                FROM dq_config.notification_policies
                WHERE rule_id = :rule_id
                """
            ),
            {"rule_id": rule_id},
        )
        row = result.mappings().first()

        if row:
            return NotificationPolicy(**row)
            
        # Insert default policy if none exists
        result = await conn.execute(
            text(
                """
                INSERT INTO dq_config.notification_policies (rule_id)
                VALUES (:rule_id)
                RETURNING *
                """
            ),
            {"rule_id": rule_id},
        )
        await conn.commit()
        
        row = result.mappings().one()
        return NotificationPolicy(**row)
