"""NewspaSync — main entrypoint.

Runs as a long-lived process inside Docker.

When WEB_ENABLED=true (default):
  - Starts the daily scheduler in the background (BackgroundScheduler)
  - Serves the web UI on port 3050 (blocking, uvicorn)

When WEB_ENABLED=false:
  - Runs the scheduler only (BlockingScheduler, no web UI)

Editions mode (config/editions.yml exists):
  - One APScheduler job per edition, each with its own schedule and delivery
  - Job IDs: edition_{id}

Legacy mode (no editions.yml):
  - Single job "daily_newspaper" using global settings
  - Identical behaviour to the original single-schedule system
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from functools import partial

from apscheduler.triggers.cron import CronTrigger

from app import config_loader as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("newspapersync")


def run_pipeline(edition: dict | None = None) -> bool:
    """Full pipeline: collect → build PDF → deliver.

    When edition is provided, uses per-edition source selection, appearance,
    and delivery config. When None, falls back to global settings (legacy mode).

    Returns True if delivery succeeded (or was not attempted via reMarkable).
    Raises on PDF generation failure.
    """
    edition_label = f"[{edition['name']}] " if edition else ""
    logger.info("━━━ %sStarting newspaper generation ━━━", edition_label)

    from app import aggregator, pdf_builder, sync
    from app.sources import learning

    logger.info("%sCollecting content from sources…", edition_label)
    context = aggregator.collect(edition)

    logger.info("%sBuilding PDF…", edition_label)
    edition_id = edition["id"] if edition else None
    pdf_path = pdf_builder.build(context, edition_id=edition_id)

    # Advance learning feed indexes now that the PDF is confirmed built.
    try:
        learning.advance_indexes()
    except Exception as exc:
        logger.warning("Could not advance learning feed indexes: %s", exc)

    # Deliver
    if edition:
        delivery = edition.get("delivery", {})
        sync_ok = True

        if delivery.get("remarkable", True):
            logger.info("%sSyncing to reMarkable…", edition_label)
            sync_ok = sync.sync(pdf_path)

        if delivery.get("email", False):
            logger.info("%sSending email copy…", edition_label)
            sync.force_email_send(pdf_path)
    else:
        # Legacy path: use global sync + optional PDF email copy
        logger.info("Syncing to reMarkable…")
        sync_ok = sync.sync(pdf_path)
        sync.send_pdf_copy(pdf_path)

    if sync_ok:
        logger.info("━━━ %sDone — newspaper delivered ━━━", edition_label)
    else:
        logger.warning("━━━ %sDone — PDF generated but sync failed ━━━", edition_label)

    return sync_ok


def main() -> None:
    web_enabled = os.environ.get("WEB_ENABLED", "true").lower() == "true"

    if web_enabled:
        _run_with_web()
    else:
        _run_scheduler_only()


# ── Scheduler-only mode (no web UI) ──────────────────────────────────────────

def _run_scheduler_only() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from app import editions as editions_module

    run_on_start = os.environ.get("RUN_ON_START", "false").lower() == "true"
    tz = cfg.get("TZ", "UTC")

    logger.info("NewspaSync starting (scheduler only)")

    if run_on_start:
        logger.info("RUN_ON_START=true — running immediately")
        if editions_module.has_editions():
            for edition in editions_module.load():
                run_pipeline(edition)
        else:
            run_pipeline()

    scheduler = BlockingScheduler(timezone=tz)
    _register_jobs(scheduler, tz, web_mode=False)

    logger.info("Scheduler running. Next runs: %s", _next_runs_str(scheduler))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("NewspaSync stopped.")


# ── Web + scheduler mode ──────────────────────────────────────────────────────

def _run_with_web() -> None:
    import threading
    import uvicorn
    from apscheduler.schedulers.background import BackgroundScheduler
    from app.web import set_scheduler, run_pipeline_tracked, run_pipeline_tracked_for_edition
    from app import editions as editions_module

    run_on_start = os.environ.get("RUN_ON_START", "false").lower() == "true"
    port = int(os.environ.get("WEB_PORT", "3050"))
    tz = cfg.get("TZ", "UTC")

    logger.info("NewspaSync starting — web UI on port %d", port)

    scheduler = BackgroundScheduler(timezone=tz)
    _register_jobs(scheduler, tz, web_mode=True)
    scheduler.start()
    set_scheduler(scheduler)

    logger.info("Scheduler running. Next runs: %s", _next_runs_str(scheduler))

    if run_on_start:
        logger.info("RUN_ON_START=true — running immediately in background")
        if editions_module.has_editions():
            for edition in editions_module.load():
                t = threading.Thread(
                    target=partial(run_pipeline_tracked_for_edition, edition["id"]),
                    daemon=True,
                )
                t.start()
        else:
            t = threading.Thread(target=run_pipeline_tracked, daemon=True)
            t.start()

    logger.info("Web UI available at http://0.0.0.0:%d", port)

    try:
        uvicorn.run(
            "app.web:app",
            host="0.0.0.0",
            port=port,
            log_level="warning",
        )
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
        logger.info("NewspaSync stopped.")


# ── Job registration ──────────────────────────────────────────────────────────

def _register_jobs(scheduler, tz: str, web_mode: bool) -> None:
    """Register APScheduler jobs — one per edition, or a single legacy job."""
    from app import editions as editions_module

    if editions_module.has_editions():
        if web_mode:
            from app.web import run_pipeline_tracked_for_edition
            for edition in editions_module.load():
                h, m = _parse_time(edition.get("schedule", "06:00"))
                scheduler.add_job(
                    partial(run_pipeline_tracked_for_edition, edition["id"]),
                    trigger=CronTrigger(hour=h, minute=m, timezone=tz),
                    id=f"edition_{edition['id']}",
                    name=edition["name"],
                    misfire_grace_time=3600,
                )
                logger.info("Registered edition '%s' at %02d:%02d", edition["name"], h, m)
        else:
            for edition in editions_module.load():
                h, m = _parse_time(edition.get("schedule", "06:00"))
                scheduler.add_job(
                    partial(run_pipeline, edition),
                    trigger=CronTrigger(hour=h, minute=m, timezone=tz),
                    id=f"edition_{edition['id']}",
                    name=edition["name"],
                    misfire_grace_time=3600,
                )
                logger.info("Registered edition '%s' at %02d:%02d", edition["name"], h, m)
    else:
        # Legacy: single job
        h, m = _parse_schedule_time()
        if web_mode:
            from app.web import run_pipeline_tracked
            fn = run_pipeline_tracked
        else:
            fn = run_pipeline
        scheduler.add_job(
            fn,
            trigger=CronTrigger(hour=h, minute=m, timezone=tz),
            id="daily_newspaper",
            name="Daily Newspaper",
            misfire_grace_time=3600,
        )
        logger.info("Registered daily newspaper at %02d:%02d", h, m)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_schedule_time() -> tuple[int, int]:
    return _parse_time(cfg.get("SCHEDULE_TIME", "06:00"))


def _parse_time(time_str: str) -> tuple[int, int]:
    try:
        hour, minute = time_str.split(":")
        return int(hour), int(minute)
    except (ValueError, AttributeError):
        logger.error("Invalid schedule time '%s' — expected HH:MM. Using 06:00.", time_str)
        return 6, 0


def _next_runs_str(scheduler) -> str:
    parts = []
    for job in scheduler.get_jobs():
        if job.next_run_time:
            parts.append(f"{job.name}: {job.next_run_time.strftime('%H:%M %Z')}")
    return ", ".join(parts) if parts else "unknown"


if __name__ == "__main__":
    # Allow manual trigger: python -m app.main --now [--edition <id>]
    if "--now" in sys.argv:
        from app import editions as editions_module
        if "--edition" in sys.argv:
            idx = sys.argv.index("--edition")
            edition_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
            edition = editions_module.get(edition_id) if edition_id else None
            if edition_id and not edition:
                logger.error("Edition '%s' not found", edition_id)
                sys.exit(1)
            run_pipeline(edition)
        elif editions_module.has_editions():
            for ed in editions_module.load():
                run_pipeline(ed)
        else:
            run_pipeline()
    else:
        main()
