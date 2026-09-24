"""TickTick source — fetches tasks due today and overdue tasks via OAuth2.

First-run setup:
  1. Create an app at https://developer.ticktick.com/manage
  2. Set TICKTICK_CLIENT_ID and TICKTICK_CLIENT_SECRET in docker-compose.yml
  3. Run: docker exec -it newspapersync python -m app.sources.ticktick --auth
     Follow the browser link, paste the redirect URL. Token is saved to
     /app/config/.ticktick_token and auto-refreshed on subsequent runs.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

_TOKEN_PATH = Path("/app/config/.ticktick_token")
_AUTH_URL = "https://ticktick.com/oauth/authorize"
_TOKEN_URL = "https://ticktick.com/oauth/token"
_API_BASE = "https://api.ticktick.com/open/v1"
_REDIRECT_URI = "http://localhost:8080"  # local, not actually serving — just for code capture


def fetch() -> list[dict]:
    if os.environ.get("TICKTICK_ENABLED", "false").lower() != "true":
        return []

    client_id = os.environ.get("TICKTICK_CLIENT_ID", "")
    client_secret = os.environ.get("TICKTICK_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("TickTick enabled but credentials not set")
        return []

    token = _load_token()
    if not token:
        logger.error("No TickTick token found. Run: docker exec -it newspapersync python -m app.sources.ticktick --auth")
        return []

    token = _maybe_refresh(token, client_id, client_secret)
    if not token:
        return []

    return _fetch_tasks(token["access_token"])


def _fetch_tasks(access_token: str) -> list[dict]:
    show_overdue = os.environ.get("TICKTICK_SHOW_OVERDUE", "true").lower() == "true"
    today = datetime.now().astimezone().date()   # the reader's day, not UTC's
    headers = {"Authorization": f"Bearer {access_token}"}

    # The Open API has no "all tasks" call: list the projects, then read each
    # one's data. The inbox is not in the project list but answers to "inbox".
    try:
        resp = requests.get(f"{_API_BASE}/project", headers=headers, timeout=10)
        resp.raise_for_status()
        projects = [(p["id"], p.get("name", "")) for p in resp.json() if not p.get("closed")]
    except Exception as exc:
        logger.error("TickTick project list failed: %s", exc)
        return []

    items: list[dict] = []
    for project_id, project_name in [("inbox", "Inbox")] + projects:
        try:
            resp = requests.get(f"{_API_BASE}/project/{project_id}/data", headers=headers, timeout=10)
            resp.raise_for_status()
            tasks = resp.json().get("tasks", []) or []
        except Exception as exc:
            logger.warning("TickTick project '%s' skipped: %s", project_name or project_id, exc)
            continue

        for task in tasks:
            if task.get("status", 0) != 0:  # 0 = incomplete
                continue
            due = _parse_due(task.get("dueDate"), task.get("timeZone"))
            if due is None:
                continue
            all_day = bool(task.get("isAllDay", False))
            due_day = due.date()

            is_today = due_day == today
            is_overdue = due_day < today
            if not (is_today or (show_overdue and is_overdue)):
                continue

            items.append({
                "type": "task",
                "source": "TickTick",
                "title": (task.get("title") or "(untitled)").strip(),
                "body": (task.get("content") or task.get("desc") or "").strip(),
                "published": _due_label(due, all_day, today),
                "meta": {
                    "overdue": is_overdue,
                    "priority": task.get("priority", 0) or 0,
                    "project": "" if project_id == "inbox" else project_name,
                    "due_time": "" if all_day else due.strftime("%H:%M"),
                },
            })

    # Overdue first, then priority (5 high → 0 none), then by time of day.
    items.sort(key=lambda t: (not t["meta"]["overdue"], -t["meta"]["priority"], t["meta"]["due_time"] or "99"))
    return items


def _parse_due(raw: str | None, tz_name: str | None) -> datetime | None:
    """TickTick sends "2026-09-24T14:00:00.000+0000". All-day tasks are
    midnight in the task's own zone, so convert there before taking the date —
    otherwise a task due today in Sydney lands on yesterday in UTC."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    try:
        return dt.astimezone(ZoneInfo(tz_name)) if tz_name else dt.astimezone()
    except Exception:
        return dt.astimezone()


def _due_label(due: datetime, all_day: bool, today) -> str:
    """"Today", "Today 14:30", "Yesterday", "3 days overdue"."""
    days = (today - due.date()).days
    if days <= 0:
        return "Today" if all_day else f"Today {due.strftime('%H:%M')}"
    if days == 1:
        return "Yesterday"
    return f"{days} days overdue"


def _load_token() -> dict | None:
    if not _TOKEN_PATH.exists():
        return None
    try:
        return json.loads(_TOKEN_PATH.read_text())
    except Exception:
        return None


def _save_token(token: dict) -> None:
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(json.dumps(token))


def _maybe_refresh(token: dict, client_id: str, client_secret: str) -> dict | None:
    expires_at = token.get("expires_at", 0)
    if expires_at and datetime.now(tz=timezone.utc).timestamp() < expires_at - 300:
        return token  # still valid
    if not token.get("refresh_token"):
        # TickTick tokens are long-lived and often come without a refresh
        # token; try the one we have rather than failing outright.
        return token
    # Refresh
    try:
        resp = requests.post(_TOKEN_URL, auth=HTTPBasicAuth(client_id, client_secret), data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        }, timeout=10)
        resp.raise_for_status()
        new_token = resp.json()
        # Some OAuth servers only return a new refresh token occasionally;
        # losing the old one would break every run after this.
        new_token.setdefault("refresh_token", token.get("refresh_token"))
        new_token["expires_at"] = datetime.now(tz=timezone.utc).timestamp() + new_token.get("expires_in", 3600)
        _save_token(new_token)
        return new_token
    except Exception as exc:
        logger.error("TickTick token refresh failed: %s", exc)
        return None


# ── Interactive auth flow ──────────────────────────────────────────────────────
def _auth_flow() -> None:
    client_id = os.environ.get("TICKTICK_CLIENT_ID", "")
    client_secret = os.environ.get("TICKTICK_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("ERROR: Set TICKTICK_CLIENT_ID and TICKTICK_CLIENT_SECRET first.")
        sys.exit(1)

    import urllib.parse
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": _REDIRECT_URI,
        "scope": "tasks:read tasks:write",
    })
    auth_link = f"{_AUTH_URL}?{params}"
    print(f"\nOpen this URL in your browser:\n\n  {auth_link}\n")
    print("After authorising, you will be redirected to a localhost URL that won't load.")
    code_input = input("Paste the full redirect URL (or just the 'code=...' value): ").strip()

    if "code=" in code_input:
        code = code_input.split("code=")[1].split("&")[0]
    else:
        code = code_input

    resp = requests.post(_TOKEN_URL, auth=HTTPBasicAuth(client_id, client_secret), data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _REDIRECT_URI,
    }, timeout=10)
    resp.raise_for_status()
    token = resp.json()
    token["expires_at"] = datetime.now(tz=timezone.utc).timestamp() + token.get("expires_in", 3600)
    _save_token(token)
    print(f"\nToken saved to {_TOKEN_PATH}. TickTick is ready.")


if __name__ == "__main__":
    if "--auth" in sys.argv:
        _auth_flow()
    else:
        print("Usage: python -m app.sources.ticktick --auth")
