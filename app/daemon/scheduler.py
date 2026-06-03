from __future__ import annotations

import asyncio
import logging
import random
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.daemon import executor, registry
from app.daemon.cron import classify_scheduler_status, cron_to_trigger
from app.db.session import close_db_engine
from app.models.responses import RuleExecutionResult, SavedRuleResponse
from app.services.schema_bootstrap import ensure_product_schema
from app.settings import get_settings

logger = logging.getLogger(__name__)


async def execute_scheduled_rule(
    rule: SavedRuleResponse,
    jitter_seconds: int | None = None,
) -> RuleExecutionResult:
    settings = get_settings()
    jitter = settings.rule_execution_jitter_seconds if jitter_seconds is None else jitter_seconds

    if jitter > 0:
        delay = random.uniform(0, jitter)
        logger.info("Delaying scheduled rule %s for %.2f seconds", rule.rule_id, delay)
        await asyncio.sleep(delay)

    logger.info("Executing scheduled rule %s: %s", rule.rule_id, rule.rule_name)
    result = await executor.execute_rule(registry.execution_request_from_saved_rule(rule))
    if result.status == "ERROR":
        logger.error(
            "Scheduled rule %s finished with error: %s",
            rule.rule_id,
            result.error.message if result.error else "unknown error",
        )
    else:
        logger.info("Scheduled rule %s finished with status %s", rule.rule_id, result.status)
    return result


async def load_scheduled_rules(scheduler: AsyncIOScheduler) -> int:
    rules = await registry.list_rules()
    scheduled_count = 0
    active_job_ids: set[str] = set()

    for rule in rules:
        scheduler_status = classify_scheduler_status(rule.is_enabled, rule.schedule_cron)
        if scheduler_status != "schedulable":
            logger.info(
                "Skipping rule %s (%s): %s",
                rule.rule_id,
                rule.rule_name,
                scheduler_status,
            )
            continue

        job_id = f"dq_rule_{rule.rule_id}"
        active_job_ids.add(job_id)
        trigger = cron_to_trigger(rule.schedule_cron or "")
        scheduler.add_job(
            execute_scheduled_rule,
            trigger=trigger,
            id=job_id,
            name=rule.rule_name,
            args=[rule],
            coalesce=True,
            misfire_grace_time=60,
            max_instances=1,
            replace_existing=True,
        )
        scheduled_count += 1
        logger.info(
            "Scheduled rule %s (%s) with cron '%s'",
            rule.rule_id,
            rule.rule_name,
            rule.schedule_cron,
        )

    for job in list(scheduler.get_jobs()):
        if job.id.startswith("dq_rule_") and job.id not in active_job_ids:
            scheduler.remove_job(job.id)
            logger.info("Removed stale scheduled job %s", job.id)

    logger.info("Loaded %s schedulable rule(s)", scheduled_count)
    return scheduled_count


async def refresh_scheduled_rules(
    scheduler: AsyncIOScheduler,
    interval_seconds: int = 60,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        logger.info("Refreshing scheduled rules from backend registry")
        await load_scheduled_rules(scheduler)


async def run_scheduler_forever() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.info("Starting Data Quality Daemon scheduler")
    await ensure_product_schema()

    scheduler = AsyncIOScheduler(timezone="UTC")
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            try:
                loop.add_signal_handler(getattr(signal, signal_name), stop_event.set)
            except NotImplementedError:
                pass

    await load_scheduled_rules(scheduler)
    scheduler.start()
    refresh_task = asyncio.create_task(refresh_scheduled_rules(scheduler))
    logger.info("Scheduler started")

    try:
        await stop_event.wait()
    finally:
        logger.info("Stopping scheduler")
        refresh_task.cancel()
        await asyncio.gather(refresh_task, return_exceptions=True)
        scheduler.shutdown(wait=False)
        await close_db_engine()


def main() -> None:
    asyncio.run(run_scheduler_forever())


if __name__ == "__main__":
    main()
