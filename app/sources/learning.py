"""Learning feed source — sequential lesson delivery.

Reads active courses from config/learning_feeds.yml.
Each course has a current_index that advances by max_lessons_per_day
after a successful PDF build (via advance_indexes()).

Curriculum JSON format (uploaded via web UI):
  {
    "title": "Git Basics",
    "description": "optional description",
    "lessons": [
      {"title": "What is Git?", "content": "Git is a ..."},
      ...
    ]
  }
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("/app/config/learning_feeds.yml")
_CURRICULA_DIR = Path("/app/config/curricula")

# Populated during fetch(); consumed and cleared by advance_indexes().
# Stores (feed_id, lessons_served) tuples.
_pending_advances: list[tuple[str, int]] = []


def fetch() -> list[dict]:
    """Return lesson blocks for all active feeds, staging them for index advancement."""
    global _pending_advances
    _pending_advances = []

    config = _load_config()
    blocks: list[dict] = []

    for feed in config.get("feeds", []):
        if not feed.get("active", True):
            continue

        try:
            curriculum = _load_curriculum(feed)
        except Exception as exc:
            logger.error("Learning feed '%s': could not load curriculum: %s", feed.get("name"), exc)
            continue

        lessons = curriculum.get("lessons", [])
        if not lessons:
            continue

        idx = int(feed.get("current_index", 0))
        max_per_day = max(1, int(feed.get("max_lessons_per_day", 1)))
        total = len(lessons)

        if idx >= total:
            logger.info("Learning feed '%s' is complete (%d/%d)", feed.get("name"), idx, total)
            continue

        served = 0
        for i in range(max_per_day):
            lesson_idx = idx + i
            if lesson_idx >= total:
                break

            lesson = lessons[lesson_idx]
            blocks.append({
                "type": "lesson",
                "title": lesson.get("title", f"Lesson {lesson_idx + 1}"),
                "body": lesson.get("content", ""),
                "source": feed.get("name", "Course"),
                "published": f"Lesson {lesson_idx + 1} of {total}",
                "meta": {
                    "feed_id": feed["id"],
                    "course_name": feed.get("name"),
                    "lesson_num": lesson_idx + 1,
                    "total_lessons": total,
                },
            })
            served += 1

        if served:
            _pending_advances.append((feed["id"], served))

    return blocks


def advance_indexes() -> None:
    """Increment current_index for feeds served in the last fetch().
    Called after a successful PDF build — not after sync, so a reMarkable
    outage won't prevent lesson progression.
    """
    if not _pending_advances:
        return

    config = _load_config()
    by_id = {f["id"]: f for f in config.get("feeds", [])}

    for feed_id, served in _pending_advances:
        feed = by_id.get(feed_id)
        if not feed:
            continue
        try:
            curriculum = _load_curriculum(feed)
            total = len(curriculum.get("lessons", []))
        except Exception:
            continue

        new_idx = min(feed.get("current_index", 0) + served, total)
        feed["current_index"] = new_idx
        if new_idx >= total:
            logger.info("Learning feed '%s' complete — all %d lessons delivered.", feed.get("name"), total)

    _save_config(config)
    _pending_advances.clear()


# ── CRUD helpers (used by web routes) ────────────────────────────────────────

def get_feeds_with_progress() -> list[dict]:
    """Return all feeds enriched with total lesson count and completion state."""
    config = _load_config()
    result = []
    for feed in config.get("feeds", []):
        enriched = dict(feed)
        try:
            curriculum = _load_curriculum(feed)
            total = len(curriculum.get("lessons", []))
            enriched["total_lessons"] = total
            enriched["complete"] = int(feed.get("current_index", 0)) >= total
            enriched["curriculum_title"] = curriculum.get("title", feed.get("name"))
            enriched["curriculum_description"] = curriculum.get("description", "")
        except Exception:
            enriched["total_lessons"] = 0
            enriched["complete"] = False
            enriched["curriculum_title"] = feed.get("name")
            enriched["curriculum_description"] = ""
        result.append(enriched)
    return result


def add_feed(name: str, curriculum: dict, max_lessons_per_day: int = 1) -> dict:
    """Save a new course. curriculum is the parsed JSON dict."""
    _CURRICULA_DIR.mkdir(parents=True, exist_ok=True)
    feed_id = str(uuid.uuid4())[:8]
    filename = f"{feed_id}.json"

    with open(_CURRICULA_DIR / filename, "w") as f:
        json.dump(curriculum, f, ensure_ascii=False, indent=2)

    feed = {
        "id": feed_id,
        "name": name,
        "active": True,
        "max_lessons_per_day": max_lessons_per_day,
        "current_index": 0,
        "curriculum_file": filename,
    }
    config = _load_config()
    config.setdefault("feeds", []).append(feed)
    _save_config(config)
    return feed


def update_feed(feed_id: str, **kwargs) -> bool:
    config = _load_config()
    for feed in config.get("feeds", []):
        if feed["id"] == feed_id:
            for key in ("name", "active", "max_lessons_per_day", "current_index"):
                if key in kwargs:
                    feed[key] = kwargs[key]
            _save_config(config)
            return True
    return False


def delete_feed(feed_id: str) -> bool:
    config = _load_config()
    feeds = config.get("feeds", [])
    target = next((f for f in feeds if f["id"] == feed_id), None)
    if not target:
        return False
    # Remove curriculum file
    try:
        (_CURRICULA_DIR / target["curriculum_file"]).unlink(missing_ok=True)
    except Exception:
        pass
    config["feeds"] = [f for f in feeds if f["id"] != feed_id]
    _save_config(config)
    return True


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_curriculum(feed: dict) -> dict:
    path = _CURRICULA_DIR / feed["curriculum_file"]
    with open(path) as f:
        return json.load(f)


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {"feeds": []}
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {"feeds": []}


def _save_config(config: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
