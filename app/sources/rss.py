"""RSS feed scraper.

Reads feed definitions from config/sources.yml and fetches articles.
Uses trafilatura for full article text extraction when the RSS summary
is too short or truncated.
"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

import feedparser
import requests
import trafilatura
import yaml

from app import config_loader as cfg
from app.sources._text import html_to_text, truncate, when

logger = logging.getLogger(__name__)

_CONFIG_PATH = "/app/config/sources.yml"
_MIN_SUMMARY_LEN = 200  # chars — below this we try full-page extraction
_TIMEOUT = 15
_USER_AGENT = "NewspaSync/2.0 (self-hosted newspaper generator)"
# Substrings of 1×1 tracking images that feeds embed in their summaries.
_PIXEL_MARKERS = ("feedburner.com/~r/", "feeds.feedburner", "/pixel", "pixel.", "doubleclick", "/t.gif")


def fetch() -> list[dict]:
    if cfg.get("RSS_ENABLED", "true").lower() != "true":
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
            data = yaml.safe_load(f) or {}
        return (data.get("rss") or {}).get("feeds") or []
    except FileNotFoundError:
        logger.warning("sources.yml not found — using empty feed list")
        return []


def _fetch_feed(feed: dict) -> list[dict]:
    url: str = feed["url"]
    label: str = feed.get("name", url)
    max_items: int = feed.get("max_items", int(cfg.get("RSS_MAX_ARTICLES_PER_FEED", "5")))
    max_body = int(cfg.get("RSS_MAX_ARTICLE_LENGTH", "1500"))

    # Download with a timeout ourselves: feedparser.parse(url) has none, so a
    # single stalled feed could hang the whole morning run.
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        logger.warning("Failed to parse feed: %s", url)
        return []

    blocks: list[dict] = []
    for entry in parsed.entries[:max_items]:
        title = html_to_text(entry.get("title", "")) or "(no title)"
        link = entry.get("link", "")

        raw_html = entry.get("summary", "") or (entry.get("content") or [{}])[0].get("value", "")
        image_url, caption = _extract_image(raw_html)
        body = html_to_text(raw_html)

        if len(body) < _MIN_SUMMARY_LEN and link:
            if image_url:
                # Picture posts (comics, photo of the day): the image is the
                # story. Scraping the page would only drag in navigation text,
                # so use the image's own caption (xkcd keeps its joke there).
                body = body or caption
            else:
                body = _extract_full(link) or body

        blocks.append({
            "type": "article",
            "source": label,
            "title": title,
            "body": truncate(body, max_body),
            "url": link,
            "published": _parse_date(entry),
            "image_url": image_url,
        })

    return blocks


def _extract_full(url: str) -> str:
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
            return re.sub(r"\s+", " ", text or "").strip()
    except Exception as exc:
        logger.debug("trafilatura failed for %s: %s", url, exc)
    return ""


def _parse_date(entry) -> str:
    """Feed timestamps are UTC; print them in the reader's local time."""
    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
    if stamp:
        try:
            return when(datetime(*stamp[:6], tzinfo=timezone.utc))
        except Exception:
            pass
    return ""


def _extract_image(raw_html: str) -> tuple[str, str]:
    """Return (src, caption) of the first real <img>, skipping tracking pixels."""
    for tag in re.findall(r"<img\b[^>]*>", raw_html or "", re.IGNORECASE):
        src = _attr(tag, "src")
        if not src or not src.startswith(("http://", "https://")):
            continue
        if _attr(tag, "width") in ("0", "1") or _attr(tag, "height") in ("0", "1"):
            continue
        if any(marker in src for marker in _PIXEL_MARKERS):
            continue
        caption = html.unescape(_attr(tag, "title") or _attr(tag, "alt")).strip()
        return src, caption
    return "", ""


def _attr(tag: str, name: str) -> str:
    m = re.search(rf'\b{name}\s*=\s*(["\'])(.*?)\1', tag, re.IGNORECASE | re.DOTALL)
    return m.group(2) if m else ""
