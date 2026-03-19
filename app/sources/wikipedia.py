"""Wikipedia Article of the Day source.

Fetches today's featured article from the Wikipedia REST API.
Controlled by WIKIPEDIA_ENABLED setting.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

_API_URL = "https://en.wikipedia.org/api/rest_v1/feed/featured/{year}/{month:02d}/{day:02d}"
_MAX_EXTRACT = 1500


def _error_block(reason: str, message: str) -> dict:
    return {
        "type": "source_error",
        "source": "wikipedia",
        "title": "Wikipedia",
        "reason": reason,
        "body": message,
    }


def fetch() -> list[dict]:
    try:
        from app import config_loader
        enabled = config_loader.get("WIKIPEDIA_ENABLED", os.environ.get("WIKIPEDIA_ENABLED", "false"))
    except Exception:
        enabled = os.environ.get("WIKIPEDIA_ENABLED", "false")

    if str(enabled).lower() != "true":
        return []

    now = datetime.now()
    url = _API_URL.format(year=now.year, month=now.month, day=now.day)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NewspaSync/2.0 (self-hosted newspaper generator)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except socket.timeout:
        logger.error("Wikipedia timed out")
        return [_error_block("timeout", "Wikipedia did not respond in time (10s timeout).")]
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            logger.error("Wikipedia timed out: %s", exc)
            return [_error_block("timeout", "Wikipedia did not respond in time (10s timeout).")]
        logger.error("Wikipedia unreachable: %s", exc)
        return [_error_block("unavailable", "Wikipedia could not be reached.")]
    except Exception as exc:
        logger.error("Wikipedia fetch failed: %s", exc)
        return [_error_block("unavailable", "Wikipedia returned an unexpected error.")]

    tfa = data.get("tfa") or {}
    if not tfa:
        logger.warning("Wikipedia response contained no 'tfa' (today's featured article)")
        return [_error_block("empty", "Wikipedia did not return a featured article for today.")]

    title = tfa.get("normalizedtitle") or tfa.get("title", "Featured Article")
    extract = tfa.get("extract", "").strip()
    thumbnail = (tfa.get("thumbnail") or {}).get("source", "")

    if len(extract) > _MAX_EXTRACT:
        extract = extract[:_MAX_EXTRACT].rsplit(" ", 1)[0] + "\u2026"

    return [{
        "type": "wikipedia",
        "title": title,
        "source": "Wikipedia",
        "published": "Article of the Day",
        "body": extract,
        "meta": {
            "thumbnail": thumbnail,
        },
    }]
