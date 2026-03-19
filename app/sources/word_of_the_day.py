"""Merriam-Webster Word of the Day source.

Fetches today's word from the Merriam-Webster RSS feed.
Controlled by WOTD_ENABLED setting.
No API key required.
"""

from __future__ import annotations

import logging
import os
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

_FEED_URL = "https://www.merriam-webster.com/wotd/feed/rss2"
_MAX_DEFINITION = 600


class _TextStripper(HTMLParser):
    """Strip HTML tags and return plain text."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(p.strip() for p in self._parts if p.strip())


def _strip_html(text: str) -> str:
    stripper = _TextStripper()
    stripper.feed(text)
    return stripper.get_text()


def _error_block(reason: str, message: str) -> dict:
    return {
        "type": "source_error",
        "source": "word_of_the_day",
        "title": "Word of the Day",
        "reason": reason,
        "body": message,
    }


def fetch() -> list[dict]:
    try:
        from app import config_loader
        enabled = config_loader.get("WOTD_ENABLED", os.environ.get("WOTD_ENABLED", "false"))
    except Exception:
        enabled = os.environ.get("WOTD_ENABLED", "false")

    if str(enabled).lower() != "true":
        return []

    try:
        import feedparser
        import requests
        resp = requests.get(
            _FEED_URL,
            timeout=10,
            headers={"User-Agent": "NewspaSync/2.0 (self-hosted newspaper generator)"},
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
    except requests.exceptions.Timeout:
        logger.error("Word of the Day feed timed out")
        return [_error_block("timeout", "Merriam-Webster did not respond in time (10s timeout).")]
    except Exception as exc:
        logger.error("Word of the Day feed failed: %s", exc)
        return [_error_block("unavailable", "The Word of the Day feed could not be reached.")]

    if not feed.entries:
        return [_error_block("empty", "No entries found in the Word of the Day feed.")]

    entry = feed.entries[0]

    # Title may be "Word of the Day: ephemeral" or just "ephemeral"
    raw_title = entry.get("title", "")
    word = raw_title.split(":", 1)[-1].strip() if ":" in raw_title else raw_title.strip()

    if not word:
        return [_error_block("empty", "Word of the Day feed did not contain a valid entry.")]

    raw_summary = entry.get("summary", entry.get("description", ""))
    definition = _strip_html(raw_summary).strip()

    if len(definition) > _MAX_DEFINITION:
        definition = definition[:_MAX_DEFINITION].rsplit(" ", 1)[0] + "\u2026"

    return [{
        "type": "word_of_the_day",
        "title": word,
        "source": "Merriam-Webster",
        "published": "Word of the Day",
        "body": definition,
        "meta": {},
    }]
