"""Job listings source.

Fetches new job ads from configured sources (Seek, Workday universities, RSS),
deduplicates against previously seen jobs, rates each listing against user
criteria, and returns only new jobs above the configured rating threshold.

Enable with JOBS_ENABLED=true in your environment / docker-compose.yml.
Configure searches and rating criteria in config/jobs.yml.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from app import config_loader as cfg

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("/app/config/jobs.yml")
_SEEN_PATH = Path("/app/config/jobs_seen.json")
_HISTORY_PATH = Path("/app/config/jobs_history.json")

_DEFAULT_CONFIG: dict = {
    "enabled": False,
    "min_rating": 2.0,
    "max_jobs_per_edition": 10,
    "seen_max_age_days": 30,
    "searches": [],
    "rating_criteria": {
        "keywords": {
            "weight": 3,
            "title_terms": [],
            "description_terms": [],
        },
        "salary": {
            "weight": 2,
            "min_preferred": 0,
            "max_preferred": 999999,
        },
        "location": {
            "weight": 2,
            "preferred": [],
        },
        "company": {
            "weight": 1,
            "preferred_keywords": [],
            "avoid_keywords": [],
        },
    },
}


def fetch() -> list[dict]:
    """Entry point called by aggregator.collect()."""
    if cfg.get("JOBS_ENABLED", "false").lower() != "true":
        return []

    config = load_config()
    if not config.get("enabled", False):
        return []

    searches = config.get("searches", [])
    if not searches:
        logger.info("Jobs: no searches configured")
        return []

    seen = _load_seen()
    history = _load_history()
    criteria = config.get("rating_criteria", {})
    min_rating = float(config.get("min_rating", 2.0))
    max_jobs = int(config.get("max_jobs_per_edition", 10))
    max_age_days = int(config.get("seen_max_age_days", 30))

    raw_jobs: list[dict] = []
    for search in searches:
        if not search.get("enabled", True):
            continue
        scraper = _get_scraper(search.get("source", ""))
        if scraper is None:
            logger.warning("Jobs: unknown source type '%s'", search.get("source"))
            continue
        try:
            fetched = scraper.search(search)
            raw_jobs.extend(fetched)
        except Exception as exc:
            logger.error("Jobs: scraper error for '%s': %s", search.get("name", "?"), exc)

    blocks: list[dict] = []
    new_seen: dict[str, str] = {}
    today = datetime.now().strftime("%Y-%m-%d")

    for job in raw_jobs:
        job_id = job.get("id", "")
        if not job_id:
            continue
        if job_id in seen:
            continue  # already reported

        rating = _score_job(job, criteria)
        in_newspaper = rating >= min_rating
        new_seen[job_id] = today

        # Archive every newly discovered job regardless of rating
        history[job_id] = {
            "id": job_id,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "salary": job.get("salary", ""),
            "description": job.get("description", "")[:500],
            "url": job.get("url", ""),
            "source": job.get("source_name", ""),
            "rating": rating,
            "rating_stars": _stars(rating),
            "date_found": today,
            "date_posted": job.get("date_posted", ""),
            "appeared_in_newspaper": in_newspaper,
        }

        if not in_newspaper:
            continue

        blocks.append({
            "type": "job",
            "title": job["title"],
            "source": job["source_name"],
            "body": job.get("description", "")[:400],
            "published": job.get("date_posted", ""),
            "meta": {
                "url": job["url"],
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "salary": job.get("salary", ""),
                "rating": rating,
                "rating_stars": _stars(rating),
                "is_new": True,
            },
        })

    # Persist deduplication state and history archive
    seen.update(new_seen)
    _purge_old(seen, max_age_days)
    _save_seen(seen)
    _purge_old_history(history, max_age_days)
    _save_history(history)

    blocks.sort(key=lambda b: b["meta"]["rating"], reverse=True)
    result = blocks[:max_jobs]
    logger.info("Jobs: returning %d new listings (of %d scraped)", len(result), len(raw_jobs))
    return result


# ── Scraper registry ──────────────────────────────────────────────────────────

def _get_scraper(source: str):
    from app.sources.job_scrapers.seek import SeekScraper
    from app.sources.job_scrapers.rss_jobs import RssJobScraper
    from app.sources.job_scrapers.workday import WorkdayScraper

    registry = {
        "seek": SeekScraper,
        "rss": RssJobScraper,
        "workday": WorkdayScraper,
    }
    cls = registry.get(source.lower())
    return cls() if cls else None


# ── Rating ────────────────────────────────────────────────────────────────────

def _score_job(job: dict, criteria: dict) -> float:
    """Return a 0.0–5.0 rating for a job based on weighted criteria."""
    total_weight = 0.0
    total_score = 0.0

    # Keyword match
    kw = criteria.get("keywords", {})
    weight = float(kw.get("weight", 0))
    if weight:
        text = (job.get("title", "") + " " + job.get("description", "")).lower()
        terms = list(kw.get("title_terms", [])) + list(kw.get("description_terms", []))
        if terms:
            matched = sum(1 for t in terms if str(t).lower() in text)
            score = matched / len(terms)
        else:
            score = 0.5  # neutral — no terms configured
        total_score += weight * score
        total_weight += weight

    # Salary match
    sal = criteria.get("salary", {})
    weight = float(sal.get("weight", 0))
    if weight:
        score = _salary_score(
            job.get("salary", ""),
            sal.get("min_preferred"),
            sal.get("max_preferred"),
        )
        total_score += weight * score
        total_weight += weight

    # Location match
    loc = criteria.get("location", {})
    weight = float(loc.get("weight", 0))
    if weight:
        preferred = [str(p).lower() for p in loc.get("preferred", [])]
        job_loc = job.get("location", "").lower()
        score = 1.0 if preferred and any(p in job_loc for p in preferred) else (0.5 if not preferred else 0.0)
        total_score += weight * score
        total_weight += weight

    # Company match
    comp = criteria.get("company", {})
    weight = float(comp.get("weight", 0))
    if weight:
        name = job.get("company", "").lower()
        preferred = [str(k).lower() for k in comp.get("preferred_keywords", [])]
        avoid = [str(k).lower() for k in comp.get("avoid_keywords", [])]
        score = 0.5  # neutral
        if preferred and any(k in name for k in preferred):
            score = 1.0
        if avoid and any(k in name for k in avoid):
            score = 0.0
        total_score += weight * score
        total_weight += weight

    if total_weight == 0:
        return 2.5  # no criteria configured — neutral
    return round((total_score / total_weight) * 5, 1)


def _salary_score(salary_str: str, min_pref, max_pref) -> float:
    """Score 0.0–1.0 based on how well the salary fits the preferred range."""
    if not salary_str:
        return 0.3  # slight penalty for missing salary info

    # Extract all numbers from the salary string
    numbers = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]+", salary_str)]
    if not numbers:
        return 0.3

    # Use single number or average of range
    job_sal = sum(numbers) / len(numbers)

    # Normalise shorthand like 90k → 90000
    if job_sal < 1000:
        job_sal *= 1000

    try:
        lo = float(min_pref or 0)
        hi = float(max_pref or 999999)
    except (TypeError, ValueError):
        return 0.5

    if lo <= job_sal <= hi:
        return 1.0
    # Partial credit within 20% outside the range
    margin = (hi - lo) * 0.2 if hi > lo else hi * 0.2
    if job_sal < lo:
        gap = lo - job_sal
        return max(0.0, 1.0 - gap / (margin + 1))
    else:
        gap = job_sal - hi
        return max(0.0, 1.0 - gap / (margin + 1))


def _stars(rating: float) -> str:
    filled = round(rating)
    filled = max(0, min(5, filled))
    return "★" * filled + "☆" * (5 - filled)


# ── Config / state I/O ────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load jobs.yml, falling back to defaults if not present."""
    if not _CONFIG_PATH.exists():
        return dict(_DEFAULT_CONFIG)
    try:
        with open(_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        # Merge top-level defaults
        merged = dict(_DEFAULT_CONFIG)
        merged.update(data)
        return merged
    except Exception as exc:
        logger.warning("Could not read jobs.yml: %s", exc)
        return dict(_DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)


def _load_seen() -> dict[str, str]:
    if not _SEEN_PATH.exists():
        return {}
    try:
        with open(_SEEN_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_seen(seen: dict[str, str]) -> None:
    _SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SEEN_PATH, "w") as f:
        json.dump(seen, f, indent=2)


def _purge_old(seen: dict[str, str], max_age_days: int) -> None:
    cutoff = datetime.now() - timedelta(days=max_age_days)
    to_delete = []
    for job_id, date_str in seen.items():
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt < cutoff:
                to_delete.append(job_id)
        except ValueError:
            pass
    for job_id in to_delete:
        del seen[job_id]


# ── History archive ───────────────────────────────────────────────────────────

def load_history() -> dict[str, dict]:
    """Return the full job history archive (job_id → job record).

    Each record contains: id, title, company, location, salary, description,
    url, source, rating, rating_stars, date_found, date_posted,
    appeared_in_newspaper.
    """
    if not _HISTORY_PATH.exists():
        return {}
    try:
        with open(_HISTORY_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _load_history() -> dict[str, dict]:
    return load_history()


def _save_history(history: dict[str, dict]) -> None:
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_HISTORY_PATH, "w") as f:
        json.dump(history, f, indent=2)


def _purge_old_history(history: dict[str, dict], max_age_days: int) -> None:
    cutoff = datetime.now() - timedelta(days=max_age_days)
    to_delete = []
    for job_id, record in history.items():
        date_str = record.get("date_found", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            if dt < cutoff:
                to_delete.append(job_id)
        except ValueError:
            pass
    for job_id in to_delete:
        del history[job_id]
