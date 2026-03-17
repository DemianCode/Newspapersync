"""NewspaSync — web UI.

FastAPI app providing a dashboard to view generated PDFs, trigger runs,
edit RSS sources, and view current configuration.

Started automatically when WEB_ENABLED=true (default).
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

app = FastAPI(title="NewspaSync")
templates = Jinja2Templates(directory="/app/app/templates/web")

# Shared state updated by both the scheduler and web-triggered runs
_state: dict = {
    "last_run": None,
    "last_status": None,  # "running" | "success" | "error"
    "last_error": None,
}

_scheduler = None
_run_lock = threading.Lock()

# Sync state (separate from pipeline state so both are visible simultaneously)
_sync_state: dict = {
    "last_sync": None,
    "last_sync_status": None,  # "running" | "success" | "error"
    "last_sync_error": None,
}
_sync_lock = threading.Lock()


def set_scheduler(sched) -> None:
    global _scheduler
    _scheduler = sched


def run_pipeline_tracked() -> None:
    """Run the pipeline and update shared state. Safe to call from any thread."""
    if not _run_lock.acquire(blocking=False):
        logger.info("Pipeline already running — skipping duplicate trigger")
        return
    try:
        from app.main import run_pipeline

        _state.update(
            {
                "last_status": "running",
                "last_run": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "last_error": None,
            }
        )
        run_pipeline()
        _state["last_status"] = "success"
    except Exception as exc:
        _state["last_status"] = "error"
        _state["last_error"] = str(exc)
        logger.exception("Pipeline failed from web trigger: %s", exc)
    finally:
        _run_lock.release()


def sync_pdf_tracked(pdf_path: Path) -> None:
    """Sync a specific PDF to reMarkable and update shared sync state."""
    if not _sync_lock.acquire(blocking=False):
        logger.info("Sync already running — skipping duplicate trigger")
        return
    try:
        from app.sync import sync

        _sync_state.update({
            "last_sync_status": "running",
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "last_sync_error": None,
        })
        success = sync(pdf_path)
        if success:
            _sync_state["last_sync_status"] = "success"
        else:
            _sync_state["last_sync_status"] = "error"
            _sync_state["last_sync_error"] = "Sync failed — check container logs"
    except Exception as exc:
        _sync_state["last_sync_status"] = "error"
        _sync_state["last_sync_error"] = str(exc)
        logger.exception("Sync failed from web trigger: %s", exc)
    finally:
        _sync_lock.release()


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    output_dir = Path("/app/output")
    pdfs = (
        sorted(output_dir.glob("newspaper-*.pdf"), reverse=True)[:10]
        if output_dir.exists()
        else []
    )
    next_run = None
    if _scheduler:
        job = _scheduler.get_job("daily_newspaper")
        if job and job.next_run_time:
            next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active": "dashboard",
            "pdfs": [p.name for p in pdfs],
            "latest_pdf": pdfs[0].name if pdfs else None,
            "state": _state,
            "sync_state": _sync_state,
            "next_run": next_run,
        },
    )


@app.get("/status")
async def status():
    return JSONResponse({**_state, **_sync_state})


@app.post("/run")
async def trigger_run():
    t = threading.Thread(target=run_pipeline_tracked, daemon=True)
    t.start()
    return RedirectResponse("/", status_code=303)


@app.post("/sync")
async def trigger_sync(request: Request):
    form = await request.form()
    filename = str(form.get("filename", "")).strip()
    if filename:
        path = Path("/app/output") / filename
        if (
            not path.exists()
            or not filename.startswith("newspaper-")
            or not filename.endswith(".pdf")
        ):
            return HTMLResponse("Not found", status_code=404)
    else:
        output_dir = Path("/app/output")
        pdfs = sorted(output_dir.glob("newspaper-*.pdf"), reverse=True) if output_dir.exists() else []
        if not pdfs:
            return RedirectResponse("/", status_code=303)
        path = pdfs[0]
    t = threading.Thread(target=sync_pdf_tracked, args=(path,), daemon=True)
    t.start()
    return RedirectResponse("/", status_code=303)


@app.get("/pdf/{filename}")
async def serve_pdf(filename: str):
    path = Path("/app/output") / filename
    if (
        not path.exists()
        or not filename.startswith("newspaper-")
        or not filename.endswith(".pdf")
    ):
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(str(path), media_type="application/pdf", filename=filename)


# ── RSS Sources ───────────────────────────────────────────────────────────────


@app.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request):
    return templates.TemplateResponse(
        "sources.html",
        {
            "request": request,
            "active": "sources",
            "feeds": _load_feeds(),
            "saved": "saved" in request.query_params,
        },
    )


@app.post("/sources/add")
async def add_feed(request: Request):
    form = await request.form()
    name = str(form.get("name", "")).strip()
    url = str(form.get("url", "")).strip()
    max_items = int(form.get("max_items") or 5)
    if name and url:
        config = _load_sources_config()
        config.setdefault("rss", {}).setdefault("feeds", []).append(
            {"name": name, "url": url, "max_items": max_items}
        )
        _save_sources_config(config)
    return RedirectResponse("/sources?saved", status_code=303)


@app.post("/sources/update")
async def update_feed(request: Request):
    form = await request.form()
    try:
        idx = int(form["index"])
    except (KeyError, ValueError):
        return RedirectResponse("/sources", status_code=303)
    config = _load_sources_config()
    feeds = config.get("rss", {}).get("feeds", [])
    if 0 <= idx < len(feeds):
        feeds[idx] = {
            "name": str(form.get("name", "")).strip(),
            "url": str(form.get("url", "")).strip(),
            "max_items": int(form.get("max_items") or 5),
        }
        _save_sources_config(config)
    return RedirectResponse("/sources?saved", status_code=303)


@app.post("/sources/delete")
async def delete_feed(request: Request):
    form = await request.form()
    try:
        idx = int(form["index"])
    except (KeyError, ValueError):
        return RedirectResponse("/sources", status_code=303)
    config = _load_sources_config()
    feeds = config.get("rss", {}).get("feeds", [])
    if 0 <= idx < len(feeds):
        feeds.pop(idx)
        _save_sources_config(config)
    return RedirectResponse("/sources?saved", status_code=303)


# ── Settings (read-only view of current env config) ───────────────────────────


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    groups = {
        "Schedule": ["SCHEDULE_TIME", "RUN_ON_START", "TZ"],
        "reMarkable": [
            "REMARKABLE_SYNC_METHOD",
            "REMARKABLE_FOLDER",
            "REMARKABLE_ARCHIVE_FOLDER",
            "REMARKABLE_ARCHIVE_KEEP_DAYS",
        ],
        "Weather": [
            "WEATHER_ENABLED",
            "WEATHER_LAT",
            "WEATHER_LON",
            "WEATHER_UNITS",
            "WEATHER_LOCATION_NAME",
        ],
        "Email inbox": [
            "EMAIL_ENABLED",
            "EMAIL_IMAP_HOST",
            "EMAIL_IMAP_PORT",
            "EMAIL_MAX_ITEMS",
        ],
        "TickTick": ["TICKTICK_ENABLED", "TICKTICK_SHOW_OVERDUE"],
        "RSS": [
            "RSS_ENABLED",
            "RSS_MAX_ARTICLES_PER_FEED",
            "RSS_MAX_ARTICLE_LENGTH",
        ],
        "AI Summaries": [
            "AI_SUMMARY_ENABLED",
            "AI_API_BASE_URL",
            "AI_MODEL",
            "AI_SUMMARY_MAX_TOKENS",
        ],
        "PDF": ["PDF_THEME", "PDF_PAPER_SIZE", "PDF_COLUMNS"],
    }
    config = {
        group: {var: os.environ.get(var, "") for var in vars_}
        for group, vars_ in groups.items()
    }
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active": "settings",
            "config": config,
        },
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_sources_config() -> dict:
    config_path = Path("/app/config/sources.yml")
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_sources_config(config: dict) -> None:
    config_path = Path("/app/config/sources.yml")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _load_feeds() -> list:
    return _load_sources_config().get("rss", {}).get("feeds", [])
