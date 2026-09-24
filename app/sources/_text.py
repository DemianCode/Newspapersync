"""Shared text helpers for sources that turn web content into print.

Everything here aims at the same thing: plain, readable text in the
reader's own time zone, with no HTML debris left over.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta

_BLOCK_JUNK = re.compile(r"<(script|style|head|noscript)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
_BREAKS = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6])\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)\]])")


def html_to_text(raw: str) -> str:
    """Strip markup, decode entities and collapse whitespace to single spaces.

    Style and script bodies are dropped rather than stripped, so an HTML
    email never leaks its CSS into the snippet.
    """
    if not raw:
        return ""
    text = _COMMENTS.sub(" ", raw)
    text = _BLOCK_JUNK.sub(" ", text)
    text = _BREAKS.sub(" ", text)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def truncate(text: str, limit: int) -> str:
    """Cut at a word boundary and add an ellipsis. A limit of 0 disables it."""
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:—–- ")
    return cut + "…"


def when(dt: datetime | None, now: datetime | None = None) -> str:
    """Short, local, human time label: "07:12", "Yesterday 21:05", "Mon 22 Sep".

    Aware datetimes are converted to the container's local zone (set TZ);
    naive ones are assumed to already be local.
    """
    if dt is None:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone()
        now = (now or datetime.now().astimezone())
        now = now.astimezone()
    else:
        now = now or datetime.now()
        now = now.replace(tzinfo=None)

    day = dt.date()
    today = now.date()
    if day == today:
        return dt.strftime("%H:%M")
    if day == today - timedelta(days=1):
        return "Yesterday " + dt.strftime("%H:%M")
    if abs((today - day).days) < 7:
        return dt.strftime("%a %H:%M")
    if day.year == today.year:
        return dt.strftime("%a %d %b").replace(" 0", " ")
    return dt.strftime("%d %b %Y").lstrip("0")
