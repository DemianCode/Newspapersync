"""NewspaSync — main entrypoint.

Runs as a long-lived process inside Docker. Schedules the daily newspaper
generation and reMarkable sync via APScheduler.

Environment variables (all set in docker-compose.yml):
  SCHEDULE_TIME  — "HH:MM" in container local time (default "06:00")
  RUN_ON_START   — "true" to also run immediately on startup
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("newspapersync")


def run_pipeline() -> None:
    """Full pipeline: collect → build PDF → sync to reMarkable."""
    logger.info("━━━ Starting newspaper generation ━━━")

    try:
        from app import aggregator, pdf_builder, sync

        logger.info("Collecting content from sources…")
        context = aggregator.collect()

        logger.info("Building PDF…")
        pdf_path = pdf_builder.build(context)

        logger.info("Syncing to reMarkable…")
        success = sync.sync(pdf_path)

        if success:
            logger.info("━━━ Done — newspaper delivered ━━━")
        else:
            logger.warning("━━━ Done — PDF generated but sync failed ━━━")

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)


def main() -> None:
    schedule_time = os.environ.get("SCHEDULE_TIME", "06:00")
    run_on_start = os.environ.get("RUN_ON_START", "false").lower() == "true"

    try:
        hour, minute = schedule_time.split(":")
        hour, minute = int(hour), int(minute)
    except ValueError:
        logger.error("Invalid SCHEDULE_TIME '%s' — expected HH:MM. Using 06:00.", schedule_time)
        hour, minute = 6, 0

    logger.info("NewspaSync starting — daily run scheduled at %02d:%02d", hour, minute)

    if run_on_start:
        logger.info("RUN_ON_START=true — running immediately")
        run_pipeline()

    scheduler = BlockingScheduler(timezone=os.environ.get("TZ", "UTC"))
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_newspaper",
        name="Daily Newspaper",
        misfire_grace_time=3600,  # run even if up to 1h late
    )

    logger.info("Scheduler running. Next run: %s", _next_run_str(scheduler))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("NewspaSync stopped.")


def _next_run_str(scheduler) -> str:
    job = scheduler.get_job("daily_newspaper")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
    return "unknown"


if __name__ == "__main__":
    # Allow manual trigger: python -m app.main --now
    if "--now" in sys.argv:
        run_pipeline()
    else:
        main()
