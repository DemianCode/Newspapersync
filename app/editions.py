"""Edition management — load/save/CRUD for newspaper editions.

An edition is a named pipeline configuration:
  - Which sources to include
  - When to run (schedule)
  - Where to deliver (reMarkable, email, or both)
  - PDF appearance overrides (theme, paper size, columns, font size)

Stored in config/editions.yml.

When no editions.yml exists the system behaves exactly as before —
a single job driven by global settings and docker-compose.yml env vars.
Editions are opt-in: create the first edition to activate the system.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import yaml

EDITIONS_PATH = Path("/app/config/editions.yml")

# Canonical source keys used in edition 'sources' dicts.
# Order here controls display order in the UI.
ALL_SOURCES: list[tuple[str, str]] = [
    ("weather",       "Weather"),
    ("tasks",         "Tasks (TickTick)"),
    ("email_inbox",   "Email Inbox"),
    ("news",          "RSS News"),
    ("learning",      "Learning Curriculum"),
    ("shell",         "Shell Snippets"),
    ("sudoku",        "Sudoku Puzzle"),
    ("wikipedia",     "Wikipedia Article of the Day"),
    ("wikiquote",     "Wikiquote Quote of the Day"),
    ("word_of_the_day", "Word of the Day"),
    ("jobs",          "Job Listings"),
]

_SOURCE_KEYS = [k for k, _ in ALL_SOURCES]


def has_editions() -> bool:
    """True if editions.yml exists and contains at least one edition."""
    if not EDITIONS_PATH.exists():
        return False
    try:
        return len(load()) > 0
    except Exception:
        return False


def load() -> list[dict]:
    """Load all editions from editions.yml. Returns [] if file missing."""
    if not EDITIONS_PATH.exists():
        return []
    try:
        with open(EDITIONS_PATH) as f:
            data = yaml.safe_load(f) or {}
        return data.get("editions", [])
    except Exception:
        return []


def save(editions: list[dict]) -> None:
    """Persist editions list to editions.yml."""
    EDITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EDITIONS_PATH, "w") as f:
        yaml.dump({"editions": editions}, f, default_flow_style=False, allow_unicode=True)


def get(edition_id: str) -> dict | None:
    """Return a specific edition by ID, or None."""
    for e in load():
        if e.get("id") == edition_id:
            return e
    return None


def create(data: dict) -> dict:
    """Create a new edition from a data dict and persist it. Returns the saved edition."""
    edition = _normalise(data)

    # Generate a clean ID from the name, ensure uniqueness
    base_id = re.sub(r"[^a-z0-9]+", "_", edition["name"].lower()).strip("_") or "edition"
    base_id = base_id[:24]
    existing_ids = {e["id"] for e in load()}
    edition["id"] = base_id
    if edition["id"] in existing_ids:
        edition["id"] = f"{base_id}_{uuid.uuid4().hex[:4]}"

    editions = load()
    editions.append(edition)
    save(editions)
    return edition


def update(edition_id: str, data: dict) -> dict | None:
    """Update an existing edition by ID. Returns updated edition or None."""
    editions = load()
    for i, e in enumerate(editions):
        if e.get("id") == edition_id:
            updated = _normalise(data)
            updated["id"] = edition_id  # preserve ID
            editions[i] = updated
            save(editions)
            return updated
    return None


def delete(edition_id: str) -> bool:
    """Delete an edition by ID. Returns True if found and deleted."""
    editions = load()
    new_editions = [e for e in editions if e.get("id") != edition_id]
    if len(new_editions) == len(editions):
        return False
    save(new_editions)
    return True


def default_sources(enabled: bool = True) -> dict:
    """Return a sources dict with all keys set to the given value."""
    return {k: enabled for k in _SOURCE_KEYS}


def default_appearance() -> dict:
    return {"theme": "traditional", "paper_size": "A5", "columns": 1, "font_size": 9}


def default_delivery() -> dict:
    return {"remarkable": True, "email": False}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _normalise(data: dict) -> dict:
    """Coerce and fill defaults for a raw edition data dict."""
    sources = {}
    for key in _SOURCE_KEYS:
        raw = data.get(f"source_{key}", data.get("sources", {}).get(key, False))
        sources[key] = _bool(raw)

    delivery = {
        "remarkable": _bool(data.get("delivery_remarkable", data.get("delivery", {}).get("remarkable", True))),
        "email":      _bool(data.get("delivery_email",      data.get("delivery", {}).get("email", False))),
    }

    appearance = {
        "theme":      str(data.get("appearance_theme",      data.get("appearance", {}).get("theme", "traditional"))),
        "paper_size": str(data.get("appearance_paper_size", data.get("appearance", {}).get("paper_size", "A5"))),
        "columns":    int(data.get("appearance_columns",    data.get("appearance", {}).get("columns", 1))),
        "font_size":  int(data.get("appearance_font_size",  data.get("appearance", {}).get("font_size", 9))),
    }

    return {
        "id": str(data.get("id", "")),
        "name": str(data.get("name", "Edition")).strip() or "Edition",
        "schedule": str(data.get("schedule", "06:00")).strip(),
        "delivery": delivery,
        "sources": sources,
        "appearance": appearance,
    }


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "on")
