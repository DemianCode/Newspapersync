"""RSS feed scraper.

Reads feed definitions from config/sources.yml and fetches articles.
Uses trafilatura for full article text extraction when the RSS summary
is too short or truncated.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import feedparser
import trafilatura
import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = "/app/config/sources.yml"
_MAX_PER_FEED = int(os.environ.get("RSS_MAX_ARTICLES_PER_FEED", "5"))
_MAX_BODY_LEN = int(os.environ.get("RSS_MAX_ARTICLE_LENGTH", "1500"))
_MIN_SUMMARY_LEN = 200  # chars — below this we try full-page extraction


def fetch() -> list[dict]:
    if os.environ.get("RSS_ENABLED", "true").lower() != "true":
        return []

    feeds = _load_feeds()
    if not feeds:
        logger.warning("No RSS feeds configured in %s", _CONFIG_PATH)
        return []

    blocks: list[dict] = []
    for feed in feeds:
        try:
            blocks.extend(_fetch_feed(feed))
        except Exception as exc:
            logger.error("RSS feed error (%s): %s", feed.get("url"), exc)

    return blocks


def _load_feeds() -> list[dict]:
    try:
        with open(_CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("rss", {}).get("feeds", [])
    except FileNotFoundError:
        logger.warning("sources.yml not found — using empty feed list")
        return []


def _fetch_feed(feed: dict) -> list[dict]:
    url: str = feed["url"]
    label: str = feed.get("name", url)
    max_items: int = feed.get("max_items", _MAX_PER_FEED)

    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        logger.warning("Failed to parse feed: %s", url)
        return []

    blocks: list[dict] = []
    for entry in parsed.entries[:max_items]:
        title = entry.get("title", "(no title)")
        link = entry.get("link", "")
        published = _parse_date(entry)

        # Try summary from feed first
        body = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
        body = _strip_html(body)

        # Fetch full article if summary is too short
        if len(body) < _MIN_SUMMARY_LEN and link:
            body = _extract_full(link) or body

        if _MAX_BODY_LEN > 0:
            body = body[:_MAX_BODY_LEN].rsplit(" ", 1)[0] + "…" if len(body) > _MAX_BODY_LEN else body

        blocks.append({
            "type": "article",
            "source": label,
            "title": title,
            "body": body,
            "url": link,
            "published": published,
        })

    return blocks


def _extract_full(url: str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            return text or ""
    except Exception as exc:
        logger.debug("trafilatura failed for %s: %s", url, exc)
    return ""


def _parse_date(entry) -> str:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.strftime("%d %b %Y, %H:%M")
        except Exception:
            pass
    return ""


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
