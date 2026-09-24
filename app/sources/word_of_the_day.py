"""Merriam-Webster Word of the Day source.

Fetches today's word from the Merriam-Webster RSS feed.
Controlled by WOTD_ENABLED setting.
No API key required.
"""

from __future__ import annotations

import logging
import os
import re

from app.sources._text import html_to_text, truncate

logger = logging.getLogger(__name__)

_FEED_URL = "https://www.merriam-webster.com/wotd/feed/rss2"
_MAX_DEFINITION = 600


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
    parts = _parse_entry(raw_summary, word)
    if not parts["definition"]:
        return [_error_block("empty", "The Word of the Day entry had no definition.")]

    return [{
        "type": "word_of_the_day",
        "title": word,
        "source": "Merriam-Webster",
        "published": "Word of the Day",
        "body": parts["definition"],
        "meta": {
            "pronunciation": parts["pronunciation"],
            "part_of_speech": parts["part_of_speech"],
            "example": parts["example"],
            "did_you_know": parts["did_you_know"],
        },
    }]


def _parse_entry(raw_html: str, word: str) -> dict:
    """Split M-W's entry into its parts instead of printing one run-on blob.

    The feed body is a series of paragraphs: a boilerplate line ("…Word of the
    Day for September 24 is:"), a header ("word • \\pron\\ • noun"), the
    definition, an example starting "//", a "See the entry" link, then
    Examples and "Did You Know?" sections.
    """
    paras = [html_to_text(p) for p in re.split(r"<\s*/?\s*(?:p|br)\b[^>]*>", raw_html or "", flags=re.I)]
    paras = [p for p in paras if p]

    out = {"pronunciation": "", "part_of_speech": "", "definition": "", "example": "", "did_you_know": ""}
    section = "definition"
    for i, para in enumerate(paras):
        low = para.lower()
        if "word of the day" in low and low.rstrip().endswith("is:"):
            continue
        if low.startswith("see the entry") or low.startswith("see the definition"):
            continue
        if low.rstrip(":?") in ("examples", "did you know"):
            section = "examples" if low.startswith("examples") else "did_you_know"
            continue
        if "•" in para and not out["part_of_speech"] and not out["definition"]:
            bits = [b.strip() for b in para.split("•")]
            for bit in bits[1:]:
                if bit.startswith("\\") or bit.startswith("/"):
                    out["pronunciation"] = bit.strip("\\/ ")
                elif bit:
                    out["part_of_speech"] = bit
            continue
        if section == "definition":
            if para.startswith("//"):
                if not out["example"]:
                    out["example"] = para.lstrip("/ ").strip()
            elif not out["definition"]:
                out["definition"] = para
        elif section == "did_you_know" and not out["did_you_know"]:
            out["did_you_know"] = para

    if not out["definition"]:
        # Unknown layout: fall back to the whole text minus the boilerplate.
        text = re.sub(r"^.*?Word of the Day for .*? is:\s*", "", html_to_text(raw_html), flags=re.I)
        out["definition"] = text

    out["definition"] = truncate(out["definition"], _MAX_DEFINITION)
    out["example"] = truncate(out["example"], 240)
    out["did_you_know"] = truncate(out["did_you_know"], 320)
    return out
