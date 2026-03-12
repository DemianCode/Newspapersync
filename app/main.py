"""NewspaSync — main entrypoint.

Runs as a long-lived process inside Docker.

When WEB_ENABLED=true (default):
  - Starts the daily scheduler in the background (BackgroundScheduler)
  - Serves the web UI on port 8080 (blocking, uvicorn)

When WEB_ENABLED=false:
  - Runs the scheduler only (BlockingScheduler, no web UI)

Environment variables (all set in docker-compose.yml):
  SCHEDULE_TIME  — "HH:MM" in container local time (default "06:00")
  RUN_ON_START   — "true" to also run immediately on startup
  WEB_ENABLED    — "true" | "false" (default "true")
  WEB_PORT       — port for the web UI (default 8080)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

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
        raise


def main() -> None:
    web_enabled = os.environ.get("WEB_ENABLED", "true").lower() == "true"

    if web_enabled:
        _run_with_web()
    else:
        _run_scheduler_only()


# ── Scheduler-only mode (no web UI) ──────────────────────────────────────────

def _run_scheduler_only() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    hour, minute = _parse_schedule_time()
    run_on_start = os.environ.get("RUN_ON_START", "false").lower() == "true"

    logger.info("NewspaSync starting (scheduler only) — daily run at %02d:%02d", hour, minute)

    if run_on_start:
        logger.info("RUN_ON_START=true — running immediately")
        run_pipeline()

    scheduler = BlockingScheduler(timezone=os.environ.get("TZ", "UTC"))
    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_newspaper",
        name="Daily Newspaper",
        misfire_grace_time=3600,
    )

    logger.info("Scheduler running. Next run: %s", _next_run_str(scheduler))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("NewspaSync stopped.")


# ── Web + scheduler mode ──────────────────────────────────────────────────────

def _run_with_web() -> None:
    import threading
    import uvicorn
    from apscheduler.schedulers.background import BackgroundScheduler
    from app.web import set_scheduler, run_pipeline_tracked

    hour, minute = _parse_schedule_time()
    run_on_start = os.environ.get("RUN_ON_START", "false").lower() == "true"
    port = int(os.environ.get("WEB_PORT", "8080"))

    logger.info(
        "NewspaSync starting — daily run at %02d:%02d — web UI on port %d",
        hour, minute, port,
    )

    scheduler = BackgroundScheduler(timezone=os.environ.get("TZ", "UTC"))
    scheduler.add_job(
        run_pipeline_tracked,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_newspaper",
        name="Daily Newspaper",
        misfire_grace_time=3600,
    )
    scheduler.start()
    set_scheduler(scheduler)

    logger.info("Scheduler running. Next run: %s", _next_run_str(scheduler))

    if run_on_start:
        logger.info("RUN_ON_START=true — running immediately in background")
        t = threading.Thread(target=run_pipeline_tracked, daemon=True)
        t.start()

    logger.info("Web UI available at http://0.0.0.0:%d", port)

    try:
        uvicorn.run(
            "app.web:app",
            host="0.0.0.0",
            port=port,
            log_level="warning",  # uvicorn access logs are noisy; app uses its own logger
        )
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
        logger.info("NewspaSync stopped.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_schedule_time() -> tuple[int, int]:
    schedule_time = os.environ.get("SCHEDULE_TIME", "06:00")
    try:
        hour, minute = schedule_time.split(":")
        return int(hour), int(minute)
    except ValueError:
        logger.error(
            "Invalid SCHEDULE_TIME '%s' — expected HH:MM. Using 06:00.", schedule_time
        )
        return 6, 0


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
