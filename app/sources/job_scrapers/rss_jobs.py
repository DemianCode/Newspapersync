"""RSS-based job feed scraper.

Works with any job board that exposes an RSS/Atom feed
(e.g. Indeed, GradConnection, JCU CareerHub, custom university feeds).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

import feedparser

from app.sources.job_scrapers.base import BaseJobScraper

logger = logging.getLogger(__name__)


class RssJobScraper(BaseJobScraper):
    def search(self, config: dict) -> list[dict]:
        rss_url = config.get("rss_url", "")
        if not rss_url:
            logger.warning("RSS job search missing rss_url in config")
            return []

        max_results = int(config.get("max_results", 20))
        keywords = config.get("keywords", "").lower()
        source_name = config.get("name", "RSS Jobs")

        parsed = feedparser.parse(rss_url)
        if parsed.bozo and not parsed.entries:
            logger.warning("Failed to parse job RSS feed: %s", rss_url)
            return []

        results = []
        for entry in parsed.entries[:max_results]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            if not title or not link:
                continue

            # Optional keyword filter
            if keywords:
                haystack = (title + " " + entry.get("summary", "")).lower()
                if keywords not in haystack:
                    continue

            job_id = "rss-" + hashlib.md5(link.encode()).hexdigest()[:12]

            # Try to extract company from various feed fields
            company = (
                entry.get("author", "")
                or _get_dc_creator(entry)
                or _extract_tag(entry, "company")
                or ""
            )

            # Location from tags or custom fields
            location = _extract_tag(entry, "location") or ""

            # Salary — rarely in RSS but try
            salary = _extract_tag(entry, "salary") or ""

            summary = _strip_html(entry.get("summary", ""))

            results.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "salary": salary,
                "description": summary[:400],
                "url": link,
                "date_posted": _parse_feed_date(entry),
                "source_name": source_name,
            })

        return results


def _get_dc_creator(entry) -> str:
    tags = getattr(entry, "tags", [])
    for tag in tags:
        if "creator" in tag.get("term", "").lower():
            return tag.get("label", "")
    return ""


def _extract_tag(entry, term: str) -> str:
    """Look for a custom tag/category matching term."""
    for tag in getattr(entry, "tags", []):
        if term.lower() in tag.get("term", "").lower():
            return tag.get("label", "")
    return ""


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_feed_date(entry) -> str:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.strftime("%d %b %Y")
        except Exception:
            pass
    return ""
