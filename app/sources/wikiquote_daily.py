"""Wikiquote Quote of the Day source.

Fetches today's featured quote from Wikiquote via the MediaWiki parse API.
Controlled by WIKIQUOTE_DAILY_ENABLED setting.
No API key required.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

_API_URL = (
    "https://en.wikiquote.org/w/api.php"
    "?action=parse&page=Wikiquote:Quote_of_the_day"
    "&prop=text&format=json&section=0"
)


class _QuoteParser(HTMLParser):
    """Extract the first blockquote and its attribution from Wikiquote page HTML."""

    def __init__(self):
        super().__init__()
        self._in_bq = False
        self._in_small = False
        self._skip_depth = 0
        self._quote_parts: list[str] = []
        self._attr_parts: list[str] = []
        self.quote = ""
        self.attribution = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "blockquote" and not self._in_bq and not self.quote:
            self._in_bq = True
        elif tag == "small" and self._in_bq:
            self._in_small = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "blockquote" and self._in_bq:
            self._in_bq = False
            self.quote = " ".join(self._quote_parts).strip()
            self.attribution = "".join(self._attr_parts).strip()
        elif tag == "small" and self._in_small:
            self._in_small = False

    def handle_data(self, data):
        if self._skip_depth or not self._in_bq:
            return
        text = data.strip()
        if not text:
            return
        if self._in_small:
            self._attr_parts.append(data)
        else:
            self._quote_parts.append(text)


def _error_block(reason: str, message: str) -> dict:
    return {
        "type": "source_error",
        "source": "wikiquote_daily",
        "title": "Quote of the Day",
        "reason": reason,
        "body": message,
    }


def fetch() -> list[dict]:
    try:
        from app import config_loader
        enabled = config_loader.get("WIKIQUOTE_DAILY_ENABLED", os.environ.get("WIKIQUOTE_DAILY_ENABLED", "false"))
    except Exception:
        enabled = os.environ.get("WIKIQUOTE_DAILY_ENABLED", "false")

    if str(enabled).lower() != "true":
        return []

    try:
        req = urllib.request.Request(
            _API_URL,
            headers={"User-Agent": "NewspaSync/2.0 (self-hosted newspaper generator)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except socket.timeout:
        logger.error("Wikiquote timed out")
        return [_error_block("timeout", "Wikiquote did not respond in time (10s timeout).")]
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            logger.error("Wikiquote timed out: %s", exc)
            return [_error_block("timeout", "Wikiquote did not respond in time (10s timeout).")]
        logger.error("Wikiquote unreachable: %s", exc)
        return [_error_block("unavailable", "Wikiquote could not be reached.")]
    except Exception as exc:
        logger.error("Wikiquote fetch failed: %s", exc)
        return [_error_block("unavailable", "Wikiquote returned an unexpected error.")]

    html_text = (data.get("parse") or {}).get("text", {}).get("*", "")
    if not html_text:
        return [_error_block("empty", "Wikiquote did not return content for today.")]

    parser = _QuoteParser()
    parser.feed(html_text)

    if not parser.quote:
        logger.warning("No blockquote found in Wikiquote QOTD page")
        return [_error_block("empty", "No quote found in today's Wikiquote content.")]

    return [{
        "type": "wikiquote",
        "title": "Quote of the Day",
        "source": "Wikiquote",
        "published": "Quote of the Day",
        "body": parser.quote,
        "meta": {
            "attribution": parser.attribution,
        },
    }]
