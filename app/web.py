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

import json

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

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        _state.update({"last_status": "running", "last_run": now, "last_error": None})
        _sync_state.update({"last_sync_status": "running", "last_sync": now, "last_sync_error": None})

        sync_ok = run_pipeline()

        _state["last_status"] = "success"
        if sync_ok:
            _sync_state["last_sync_status"] = "success"
        else:
            _sync_state["last_sync_status"] = "error"
            _sync_state["last_sync_error"] = "Sync failed — check container logs"
    except Exception as exc:
        _state["last_status"] = "error"
        _state["last_error"] = str(exc)
        _sync_state["last_sync_status"] = None  # didn't reach sync step
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
    return FileResponse(
        str(path),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


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


# ── Settings ──────────────────────────────────────────────────────────────────


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    # Read-only groups — require docker-compose.yml edits to change
    groups = {
        "reMarkable": [
            "REMARKABLE_SYNC_METHOD",
            "REMARKABLE_FOLDER",
            "REMARKABLE_ARCHIVE_FOLDER",
            "REMARKABLE_ARCHIVE_KEEP_DAYS",
        ],
        "TickTick": ["TICKTICK_ENABLED", "TICKTICK_SHOW_OVERDUE"],
        "AI Summaries": [
            "AI_SUMMARY_ENABLED",
            "AI_API_BASE_URL",
            "AI_MODEL",
            "AI_SUMMARY_MAX_TOKENS",
        ],
    }
    from app import config_loader
    # Effective value = settings.yml override OR env var (same priority as runtime)
    def eff(key: str, default: str = "") -> str:
        return config_loader.get(key, os.environ.get(key, default))

    editable = {
        "Weather": {
            "WEATHER_ENABLED":       eff("WEATHER_ENABLED", "true"),
            "WEATHER_LAT":           eff("WEATHER_LAT", ""),
            "WEATHER_LON":           eff("WEATHER_LON", ""),
            "WEATHER_UNITS":         eff("WEATHER_UNITS", "celsius"),
            "WEATHER_LOCATION_NAME": eff("WEATHER_LOCATION_NAME", ""),
        },
        "Schedule": {
            "SCHEDULE_TIME": eff("SCHEDULE_TIME", "06:00"),
            "TZ":            eff("TZ", "UTC"),
        },
        "RSS": {
            "RSS_ENABLED":                eff("RSS_ENABLED", "true"),
            "RSS_MAX_ARTICLES_PER_FEED":  eff("RSS_MAX_ARTICLES_PER_FEED", "5"),
            "RSS_MAX_ARTICLE_LENGTH":     eff("RSS_MAX_ARTICLE_LENGTH", "1500"),
        },
        "Email": {
            "EMAIL_ENABLED":    eff("EMAIL_ENABLED", "false"),
            "EMAIL_IMAP_HOST":  eff("EMAIL_IMAP_HOST", ""),
            "EMAIL_IMAP_PORT":  eff("EMAIL_IMAP_PORT", "993"),
            "EMAIL_MAX_ITEMS":  eff("EMAIL_MAX_ITEMS", "10"),
        },
        "Wikipedia": {
            "WIKIPEDIA_ENABLED": eff("WIKIPEDIA_ENABLED", "false"),
        },
        "WikiquoteDaily": {
            "WIKIQUOTE_DAILY_ENABLED": eff("WIKIQUOTE_DAILY_ENABLED", "false"),
        },
        "WordOfDay": {
            "WOTD_ENABLED": eff("WOTD_ENABLED", "false"),
        },
        "Sudoku": {
            "SUDOKU_ENABLED":    eff("SUDOKU_ENABLED", "false"),
            "SUDOKU_DIFFICULTY": eff("SUDOKU_DIFFICULTY", "medium"),
        },
    }

    readonly_config = {
        group: {var: os.environ.get(var, "") for var in vars_}
        for group, vars_ in groups.items()
    }
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active": "settings",
            "editable": editable,
            "config": readonly_config,
            "appearance": _load_appearance(),
            "saved": "saved" in request.query_params,
        },
    )


@app.post("/settings/update")
async def save_settings(request: Request):
    """Save any non-secret settings to config/settings.yml."""
    from app import config_loader
    form = await request.form()
    updates: dict = {}

    # Weather
    for key in ("WEATHER_ENABLED", "WEATHER_LAT", "WEATHER_LON",
                "WEATHER_UNITS", "WEATHER_LOCATION_NAME"):
        if key in form:
            updates[key] = str(form[key]).strip()

    # RSS
    for key in ("RSS_ENABLED", "RSS_MAX_ARTICLES_PER_FEED", "RSS_MAX_ARTICLE_LENGTH"):
        if key in form:
            updates[key] = str(form[key]).strip()

    # Email (non-secret)
    for key in ("EMAIL_ENABLED", "EMAIL_IMAP_HOST", "EMAIL_IMAP_PORT", "EMAIL_MAX_ITEMS"):
        if key in form:
            updates[key] = str(form[key]).strip()

    # Wikipedia
    for key in ("WIKIPEDIA_ENABLED",):
        if key in form:
            updates[key] = str(form[key]).strip()

    # Wikiquote Daily
    for key in ("WIKIQUOTE_DAILY_ENABLED",):
        if key in form:
            updates[key] = str(form[key]).strip()

    # Word of the Day
    for key in ("WOTD_ENABLED",):
        if key in form:
            updates[key] = str(form[key]).strip()

    # Sudoku
    for key in ("SUDOKU_ENABLED", "SUDOKU_DIFFICULTY"):
        if key in form:
            updates[key] = str(form[key]).strip()

    # Schedule — needs restart to affect the running APScheduler
    if "SCHEDULE_TIME" in form:
        val = str(form["SCHEDULE_TIME"]).strip()
        parts = val.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            updates["SCHEDULE_TIME"] = val
    if "TZ" in form:
        tz_val = str(form["TZ"]).strip()
        if tz_val:
            updates["TZ"] = tz_val

    if updates:
        config_loader.save(updates)

    return RedirectResponse("/settings?saved", status_code=303)


@app.post("/settings/appearance")
async def save_appearance(request: Request):
    form = await request.form()
    data = {
        "newspaper_name": str(form.get("newspaper_name", "The Daily Digest")).strip() or "The Daily Digest",
        "theme": str(form.get("theme", "traditional")),
        "font_size": max(7, min(16, int(form.get("font_size") or 9))),
        "paper_size": str(form.get("paper_size", "A5")),
        "columns": max(1, min(2, int(form.get("columns") or 1))),
    }
    if data["theme"] not in ("traditional", "retro", "readable"):
        data["theme"] = "traditional"
    if data["paper_size"] not in ("A5", "A4"):
        data["paper_size"] = "A5"
    _save_appearance(data)
    return RedirectResponse("/settings?saved", status_code=303)


# ── Helpers ───────────────────────────────────────────────────────────────────

_APPEARANCE_DEFAULTS = {
    "newspaper_name": "The Daily Digest",
    "theme": "traditional",
    "font_size": 9,
    "paper_size": "A5",
    "columns": 1,
}


def _load_appearance() -> dict:
    path = Path("/app/config/appearance.yml")
    result = dict(_APPEARANCE_DEFAULTS)
    if path.exists():
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            result.update({k: v for k, v in data.items() if k in result})
        except Exception:
            pass
    return result


def _save_appearance(data: dict) -> None:
    path = Path("/app/config/appearance.yml")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


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


# ── Learning Feeds ─────────────────────────────────────────────────────────────


@app.get("/learning", response_class=HTMLResponse)
async def learning_page(request: Request):
    from app.sources import learning
    return templates.TemplateResponse(
        "learning.html",
        {
            "request": request,
            "active": "learning",
            "feeds": learning.get_feeds_with_progress(),
            "saved": "saved" in request.query_params,
            "error": request.query_params.get("error", ""),
        },
    )


@app.post("/learning/add")
async def add_learning_feed(request: Request):
    from app.sources import learning
    form = await request.form()
    name = str(form.get("name", "")).strip()
    max_per_day = max(1, int(form.get("max_lessons_per_day") or 1))
    file = form.get("curriculum_file")

    if not name or not file:
        return RedirectResponse("/learning?error=Name+and+curriculum+file+are+required", status_code=303)

    try:
        content = await file.read()
        curriculum = json.loads(content)
        if not isinstance(curriculum.get("lessons"), list) or not curriculum["lessons"]:
            raise ValueError("curriculum must have a non-empty 'lessons' array")
    except (json.JSONDecodeError, ValueError) as exc:
        return RedirectResponse(f"/learning?error={str(exc)[:120]}", status_code=303)

    learning.add_feed(name, curriculum, max_per_day)
    return RedirectResponse("/learning?saved", status_code=303)


@app.post("/learning/update")
async def update_learning_feed(request: Request):
    from app.sources import learning
    form = await request.form()
    feed_id = str(form.get("id", "")).strip()
    name = str(form.get("name", "")).strip()
    active = form.get("active") == "true"
    max_per_day = max(1, int(form.get("max_lessons_per_day") or 1))
    learning.update_feed(feed_id, name=name, active=active, max_lessons_per_day=max_per_day)
    return RedirectResponse("/learning?saved", status_code=303)


@app.post("/learning/reset")
async def reset_learning_feed(request: Request):
    from app.sources import learning
    form = await request.form()
    feed_id = str(form.get("id", "")).strip()
    learning.update_feed(feed_id, current_index=0)
    return RedirectResponse("/learning?saved", status_code=303)


@app.post("/learning/delete")
async def delete_learning_feed(request: Request):
    from app.sources import learning
    form = await request.form()
    feed_id = str(form.get("id", "")).strip()
    learning.delete_feed(feed_id)
    return RedirectResponse("/learning", status_code=303)


# ── Shell Snippets ─────────────────────────────────────────────────────────────


@app.get("/shell", response_class=HTMLResponse)
async def shell_page(request: Request):
    from app.sources import shell
    return templates.TemplateResponse(
        "shell.html",
        {
            "request": request,
            "active": "shell",
            "snippets": shell.get_snippets(),
            "saved": "saved" in request.query_params,
        },
    )


@app.post("/shell/add")
async def add_shell_snippet(request: Request):
    from app.sources import shell
    form = await request.form()
    name = str(form.get("name", "")).strip()
    command = str(form.get("command", "")).strip()
    timeout = max(1, min(60, int(form.get("timeout") or 10)))
    if name and command:
        shell.add_snippet(name, command, timeout)
    return RedirectResponse("/shell?saved", status_code=303)


@app.post("/shell/update")
async def update_shell_snippet(request: Request):
    from app.sources import shell
    form = await request.form()
    snippet_id = str(form.get("id", "")).strip()
    name = str(form.get("name", "")).strip()
    command = str(form.get("command", "")).strip()
    active = form.get("active") == "true"
    timeout = max(1, min(60, int(form.get("timeout") or 10)))
    shell.update_snippet(snippet_id, name=name, command=command, active=active, timeout=timeout)
    return RedirectResponse("/shell?saved", status_code=303)


@app.post("/shell/delete")
async def delete_shell_snippet(request: Request):
    from app.sources import shell
    form = await request.form()
    snippet_id = str(form.get("id", "")).strip()
    shell.delete_snippet(snippet_id)
    return RedirectResponse("/shell", status_code=303)


@app.post("/shell/test")
async def test_shell_snippet(request: Request):
    from app.sources import shell
    form = await request.form()
    command = str(form.get("command", "")).strip()
    timeout = max(1, min(30, int(form.get("timeout") or 10)))
    if not command:
        return JSONResponse({"output": "", "error": "No command provided"})
    output, error = shell.run_test(command, timeout)
    return JSONResponse({"output": output, "error": error})
