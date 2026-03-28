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
from functools import partial
from pathlib import Path

import json

import yaml
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

app = FastAPI(title="NewspaSync")
templates = Jinja2Templates(directory="/app/app/templates/web")

# ── Legacy (single-edition) state ────────────────────────────────────────────
_state: dict = {
    "last_run": None,
    "last_status": None,  # "running" | "success" | "error"
    "last_error": None,
}
_run_lock = threading.Lock()

_sync_state: dict = {
    "last_sync": None,
    "last_sync_status": None,  # "running" | "success" | "error"
    "last_sync_error": None,
}
_sync_lock = threading.Lock()

# ── Per-edition state (editions mode) ────────────────────────────────────────
_edition_states: dict = {}       # edition_id → {last_run, last_status, …}
_edition_run_locks: dict = {}    # edition_id → threading.Lock()
_edition_locks_mutex = threading.Lock()

_scheduler = None


def set_scheduler(sched) -> None:
    global _scheduler
    _scheduler = sched


def _get_edition_state(edition_id: str) -> dict:
    if edition_id not in _edition_states:
        _edition_states[edition_id] = {
            "last_run": None, "last_status": None, "last_error": None,
            "last_sync": None, "last_sync_status": None, "last_sync_error": None,
        }
    return _edition_states[edition_id]


def _get_edition_lock(edition_id: str) -> threading.Lock:
    with _edition_locks_mutex:
        if edition_id not in _edition_run_locks:
            _edition_run_locks[edition_id] = threading.Lock()
        return _edition_run_locks[edition_id]


def _parse_time(time_str: str) -> tuple[int, int]:
    try:
        h, m = time_str.strip().split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return 6, 0


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


def run_pipeline_tracked_for_edition(edition_id: str) -> None:
    """Run the pipeline for a specific edition and update its per-edition state."""
    from app import editions as editions_module
    edition = editions_module.get(edition_id)
    if not edition:
        logger.error("Edition '%s' not found — aborting", edition_id)
        return

    lock = _get_edition_lock(edition_id)
    if not lock.acquire(blocking=False):
        logger.info("Edition '%s' already running — skipping duplicate trigger", edition_id)
        return

    try:
        from app.main import run_pipeline

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        state = _get_edition_state(edition_id)
        state.update({
            "last_run": now, "last_status": "running", "last_error": None,
            "last_sync": now, "last_sync_status": "running", "last_sync_error": None,
        })

        sync_ok = run_pipeline(edition)

        state["last_status"] = "success"
        if sync_ok:
            state["last_sync_status"] = "success"
        else:
            state["last_sync_status"] = "error"
            state["last_sync_error"] = "Sync failed — check container logs"
    except Exception as exc:
        state = _get_edition_state(edition_id)
        state["last_status"] = "error"
        state["last_error"] = str(exc)
        state["last_sync_status"] = None
        logger.exception("Edition '%s' pipeline failed: %s", edition_id, exc)
    finally:
        lock.release()


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
    from app import editions as editions_module

    output_dir = Path("/app/output")
    pdfs = (
        sorted(output_dir.glob("newspaper-*.pdf"), reverse=True)[:10]
        if output_dir.exists()
        else []
    )

    editions_mode = editions_module.has_editions()

    if editions_mode:
        editions_list = editions_module.load()
        edition_states = {e["id"]: _get_edition_state(e["id"]) for e in editions_list}
        edition_next_runs: dict = {}
        if _scheduler:
            for e in editions_list:
                job = _scheduler.get_job(f"edition_{e['id']}")
                if job and job.next_run_time:
                    edition_next_runs[e["id"]] = job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")

        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "active": "dashboard",
                "pdfs": [p.name for p in pdfs],
                "latest_pdf": pdfs[0].name if pdfs else None,
                "editions_mode": True,
                "editions": editions_list,
                "edition_states": edition_states,
                "edition_next_runs": edition_next_runs,
                "state": _state,
                "sync_state": _sync_state,
                "next_run": None,
            },
        )
    else:
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
                "editions_mode": False,
                "state": _state,
                "sync_state": _sync_state,
                "next_run": next_run,
            },
        )


@app.get("/status")
async def status():
    from app import editions as editions_module
    if editions_module.has_editions():
        return JSONResponse({
            "editions_mode": True,
            "editions": {
                e["id"]: _get_edition_state(e["id"])
                for e in editions_module.load()
            },
        })
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


_RMAPI_DIR = Path("/root/.local/share/rmapi")


def _rmapi_is_authenticated() -> bool:
    """Check auth by running rmapi non-interactively — the only reliable method."""
    import shutil
    import subprocess

    if not shutil.which("rmapi"):
        return False
    try:
        result = subprocess.run(
            ["rmapi", "-ni", "ls", "/"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _rmapi_dir_has_files() -> bool:
    """Quick file-existence check used for the status badge (no network call)."""
    return _RMAPI_DIR.exists() and any(_RMAPI_DIR.iterdir())


@app.post("/settings/remarkable-auth")
async def remarkable_auth(request: Request):
    """Exchange a reMarkable one-time code for an rmapi token via the web UI."""
    import shutil
    import subprocess
    from urllib.parse import quote_plus

    form = await request.form()
    code = str(form.get("code", "")).strip()

    if not code:
        return RedirectResponse("/settings?remarkable_auth=error&msg=No+code+entered", status_code=303)

    if not shutil.which("rmapi"):
        return RedirectResponse("/settings?remarkable_auth=error&msg=rmapi+binary+not+found", status_code=303)

    try:
        # Send the one-time code then `exit` to close the interactive shell.
        # rmapi reads the code line, authenticates with reMarkable, saves the
        # token, opens its shell, then receives `exit` and quits cleanly.
        proc = subprocess.run(
            ["rmapi"],
            input=f"{code}\nexit\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Verify auth actually works via a non-interactive rmapi command,
        # rather than relying on a specific token filename.
        verify = subprocess.run(
            ["rmapi", "-ni", "ls", "/"],
            capture_output=True, text=True, timeout=15,
        )
        if verify.returncode == 0:
            return RedirectResponse("/settings?remarkable_auth=success", status_code=303)

        # Auth failed — surface whatever rmapi printed
        output = (proc.stdout + proc.stderr + verify.stdout + verify.stderr).strip()
        msg = quote_plus(output[:120]) if output else "Auth+failed+-+check+the+code+and+try+again"
        return RedirectResponse(f"/settings?remarkable_auth=error&msg={msg}", status_code=303)
    except subprocess.TimeoutExpired:
        return RedirectResponse(
            "/settings?remarkable_auth=error&msg=Timed+out+after+30s+-+check+network+connectivity",
            status_code=303,
        )
    except Exception as exc:
        from urllib.parse import quote_plus
        return RedirectResponse(
            f"/settings?remarkable_auth=error&msg={quote_plus(str(exc)[:120])}",
            status_code=303,
        )


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
        "PdfEmail": {
            "PDF_EMAIL_ENABLED":   eff("PDF_EMAIL_ENABLED", "false"),
            "PDF_EMAIL_RECIPIENT": eff("PDF_EMAIL_RECIPIENT", ""),
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
            "remarkable_authenticated": _rmapi_dir_has_files(),
            "remarkable_auth": request.query_params.get("remarkable_auth"),
            "remarkable_auth_msg": request.query_params.get("msg", ""),
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

    # PDF email delivery
    for key in ("PDF_EMAIL_ENABLED", "PDF_EMAIL_RECIPIENT"):
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

    # Schedule — live-reschedule the running APScheduler job
    new_schedule_time = None
    if "SCHEDULE_TIME" in form:
        val = str(form["SCHEDULE_TIME"]).strip()
        parts = val.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            updates["SCHEDULE_TIME"] = val
            new_schedule_time = val
    if "TZ" in form:
        tz_val = str(form["TZ"]).strip()
        if tz_val:
            updates["TZ"] = tz_val

    if updates:
        config_loader.save(updates)

    # Live-reschedule daily_newspaper job without requiring a restart
    if new_schedule_time and _scheduler:
        try:
            h, m = _parse_time(new_schedule_time)
            tz = updates.get("TZ", os.environ.get("TZ", "UTC"))
            _scheduler.reschedule_job(
                "daily_newspaper",
                trigger=CronTrigger(hour=h, minute=m, timezone=tz),
            )
            logger.info("Rescheduled daily_newspaper to %s", new_schedule_time)
        except Exception as exc:
            logger.warning("Could not live-reschedule daily_newspaper: %s", exc)

    return RedirectResponse("/settings?saved", status_code=303)


# ── Editions ──────────────────────────────────────────────────────────────────


@app.get("/editions", response_class=HTMLResponse)
async def editions_page(request: Request):
    from app import editions as editions_module
    return templates.TemplateResponse(
        "editions.html",
        {
            "request": request,
            "active": "editions",
            "editions": editions_module.load(),
            "all_sources": editions_module.ALL_SOURCES,
            "saved": "saved" in request.query_params,
            "error": request.query_params.get("error", ""),
        },
    )


@app.post("/editions/create")
async def create_edition(request: Request):
    from app import editions as editions_module
    form = await request.form()
    try:
        edition = editions_module.create(dict(form))
        if _scheduler:
            h, m = _parse_time(edition["schedule"])
            tz = os.environ.get("TZ", "UTC")
            _scheduler.add_job(
                partial(run_pipeline_tracked_for_edition, edition["id"]),
                trigger=CronTrigger(hour=h, minute=m, timezone=tz),
                id=f"edition_{edition['id']}",
                name=edition["name"],
                misfire_grace_time=3600,
            )
    except Exception as exc:
        return RedirectResponse(f"/editions?error={str(exc)[:120]}", status_code=303)
    return RedirectResponse("/editions?saved", status_code=303)


@app.post("/editions/{edition_id}/update")
async def update_edition(edition_id: str, request: Request):
    from app import editions as editions_module
    form = await request.form()
    edition = editions_module.update(edition_id, dict(form))
    if edition and _scheduler:
        h, m = _parse_time(edition["schedule"])
        tz = os.environ.get("TZ", "UTC")
        job_id = f"edition_{edition_id}"
        try:
            _scheduler.reschedule_job(
                job_id,
                trigger=CronTrigger(hour=h, minute=m, timezone=tz),
            )
            # Also update the job name if it changed
            job = _scheduler.get_job(job_id)
            if job:
                job.name = edition["name"]
        except Exception:
            pass  # job might not exist yet if scheduler was restarted
    return RedirectResponse("/editions?saved", status_code=303)


@app.post("/editions/{edition_id}/delete")
async def delete_edition(edition_id: str, request: Request):
    from app import editions as editions_module
    editions_module.delete(edition_id)
    if _scheduler:
        try:
            _scheduler.remove_job(f"edition_{edition_id}")
        except Exception:
            pass
    return RedirectResponse("/editions", status_code=303)


@app.post("/editions/{edition_id}/run")
async def run_edition_now(edition_id: str):
    t = threading.Thread(
        target=partial(run_pipeline_tracked_for_edition, edition_id),
        daemon=True,
    )
    t.start()
    return RedirectResponse("/", status_code=303)


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


# ── Jobs ──────────────────────────────────────────────────────────────────────


def _load_jobs_config() -> dict:
    from app.sources.jobs import load_config
    return load_config()


def _save_jobs_config(config: dict) -> None:
    from app.sources.jobs import save_config
    save_config(config)


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request):
    config = _load_jobs_config()
    return templates.TemplateResponse(
        "jobs.html",
        {
            "request": request,
            "active": "jobs",
            "config": config,
            "saved": "saved" in request.query_params,
        },
    )


@app.post("/jobs/settings")
async def update_jobs_settings(request: Request):
    form = await request.form()
    config = _load_jobs_config()
    config["enabled"] = form.get("enabled") == "on"
    try:
        config["min_rating"] = float(form.get("min_rating") or 2.0)
    except ValueError:
        pass
    try:
        config["max_jobs_per_edition"] = int(form.get("max_jobs_per_edition") or 10)
    except ValueError:
        pass
    try:
        config["seen_max_age_days"] = int(form.get("seen_max_age_days") or 30)
    except ValueError:
        pass
    _save_jobs_config(config)
    return RedirectResponse("/jobs?saved", status_code=303)


@app.post("/jobs/search/add")
async def add_job_search(request: Request):
    form = await request.form()
    source = str(form.get("source", "seek")).strip()
    search: dict = {
        "id": str(form.get("id", "")).strip() or f"{source}-{int(__import__('time').time())}",
        "name": str(form.get("name", "")).strip() or source,
        "source": source,
        "keywords": str(form.get("keywords", "")).strip(),
        "max_results": int(form.get("max_results") or 20),
        "enabled": form.get("enabled") == "on",
    }
    if source == "seek":
        search["location"] = str(form.get("location", "")).strip()
    elif source == "workday":
        search["workday_tenant"] = str(form.get("workday_tenant", "")).strip()
        search["workday_instance"] = str(form.get("workday_instance", "")).strip()
        search["workday_path"] = str(form.get("workday_path", "")).strip()
    elif source == "rss":
        search["rss_url"] = str(form.get("rss_url", "")).strip()

    config = _load_jobs_config()
    config.setdefault("searches", []).append(search)
    _save_jobs_config(config)
    return RedirectResponse("/jobs?saved", status_code=303)


@app.post("/jobs/search/update")
async def update_job_search(request: Request):
    form = await request.form()
    try:
        idx = int(form["index"])
    except (KeyError, ValueError):
        return RedirectResponse("/jobs", status_code=303)

    config = _load_jobs_config()
    searches = config.get("searches", [])
    if not (0 <= idx < len(searches)):
        return RedirectResponse("/jobs", status_code=303)

    source = str(form.get("source", searches[idx].get("source", "seek"))).strip()
    updated: dict = {
        "id": str(form.get("id", searches[idx].get("id", ""))).strip(),
        "name": str(form.get("name", "")).strip(),
        "source": source,
        "keywords": str(form.get("keywords", "")).strip(),
        "max_results": int(form.get("max_results") or 20),
        "enabled": form.get("enabled") == "on",
    }
    if source == "seek":
        updated["location"] = str(form.get("location", "")).strip()
    elif source == "workday":
        updated["workday_tenant"] = str(form.get("workday_tenant", "")).strip()
        updated["workday_instance"] = str(form.get("workday_instance", "")).strip()
        updated["workday_path"] = str(form.get("workday_path", "")).strip()
    elif source == "rss":
        updated["rss_url"] = str(form.get("rss_url", "")).strip()

    searches[idx] = updated
    _save_jobs_config(config)
    return RedirectResponse("/jobs?saved", status_code=303)


@app.post("/jobs/search/delete")
async def delete_job_search(request: Request):
    form = await request.form()
    try:
        idx = int(form["index"])
    except (KeyError, ValueError):
        return RedirectResponse("/jobs", status_code=303)
    config = _load_jobs_config()
    searches = config.get("searches", [])
    if 0 <= idx < len(searches):
        searches.pop(idx)
    _save_jobs_config(config)
    return RedirectResponse("/jobs?saved", status_code=303)


@app.post("/jobs/criteria/update")
async def update_jobs_criteria(request: Request):
    form = await request.form()
    config = _load_jobs_config()
    criteria = config.setdefault("rating_criteria", {})

    # Keywords
    kw = criteria.setdefault("keywords", {})
    try:
        kw["weight"] = int(form.get("kw_weight") or 3)
    except ValueError:
        pass
    kw["title_terms"] = [t.strip() for t in str(form.get("title_terms", "")).split(",") if t.strip()]
    kw["description_terms"] = [t.strip() for t in str(form.get("description_terms", "")).split(",") if t.strip()]

    # Salary
    sal = criteria.setdefault("salary", {})
    try:
        sal["weight"] = int(form.get("sal_weight") or 2)
        sal["min_preferred"] = int(form.get("sal_min") or 0)
        sal["max_preferred"] = int(form.get("sal_max") or 999999)
    except ValueError:
        pass

    # Location
    loc = criteria.setdefault("location", {})
    try:
        loc["weight"] = int(form.get("loc_weight") or 2)
    except ValueError:
        pass
    loc["preferred"] = [t.strip() for t in str(form.get("loc_preferred", "")).split(",") if t.strip()]

    # Company
    comp = criteria.setdefault("company", {})
    try:
        comp["weight"] = int(form.get("comp_weight") or 1)
    except ValueError:
        pass
    comp["preferred_keywords"] = [t.strip() for t in str(form.get("comp_preferred", "")).split(",") if t.strip()]
    comp["avoid_keywords"] = [t.strip() for t in str(form.get("comp_avoid", "")).split(",") if t.strip()]

    _save_jobs_config(config)
    return RedirectResponse("/jobs?saved", status_code=303)


@app.get("/jobs/history", response_class=HTMLResponse)
async def jobs_history_page(request: Request):
    from app.sources.jobs import load_history

    history = load_history()

    # Sort newest-first, then by rating descending within the same day
    jobs_list = sorted(
        history.values(),
        key=lambda j: (j.get("date_found", ""), j.get("rating", 0)),
        reverse=True,
    )

    # Unique dates for the date-filter dropdown
    dates = sorted({j.get("date_found", "") for j in jobs_list if j.get("date_found")}, reverse=True)

    return templates.TemplateResponse(
        "jobs_history.html",
        {
            "request": request,
            "active": "jobs",
            "jobs": jobs_list,
            "dates": dates,
            "total": len(jobs_list),
        },
    )
