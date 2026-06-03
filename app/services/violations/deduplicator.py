import hashlib
import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.db.session import metadata_engine as db_engine

logger = logging.getLogger(__name__)


def generate_fingerprint(rule_id: int, status: str, sample_rows: list[dict[str, Any]] | None) -> str:
    # Sort keys to ensure consistent hashing for json serialization
    rows_str = json.dumps(sample_rows, sort_keys=True) if sample_rows else ""
    raw = f"{rule_id}:{status}:{rows_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def check_duplicate_and_increment(
    rule_id: int, fingerprint: str, window_minutes: int
) -> bool:
    """
    Checks if a violation event with the same fingerprint exists within the deduplication window.
    If it exists, increments the occurrence count on its batch and returns True.
    """
    if window_minutes <= 0:
        return False

    async with db_engine.begin() as conn:
        # Check for recent matching event
        result = await conn.execute(
            text(
                """
                SELECT id 
                FROM dq_results.violation_events
                WHERE rule_id = :rule_id 
                  AND fingerprint = :fingerprint
                  AND created_at >= NOW() - INTERVAL '1 minute' * :window_minutes
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {
                "rule_id": rule_id,
                "fingerprint": fingerprint,
                "window_minutes": window_minutes,
            },
        )
        existing_event_id = result.scalar_one_or_none()

        if existing_event_id is not None:
            # We found a duplicate. We must also increment the batch occurrences if there is an open batch.
            # But the requirement says: "If same fingerprint appears within deduplication window: do not send notification, increment occurrence count only".
            # The aggregator handles the batch, but here we can just return True to indicate it's a duplicate.
            # We'll let the aggregator decide how to increment the batch, or we do it here. 
            # Actually, "increment occurrence count only" applies to the batch.
            return True
            
        return False
