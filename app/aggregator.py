"""Aggregator — collects content from all enabled sources.

Optionally runs AI summarisation if configured.
Returns a structured context dict consumed by the PDF builder.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_APPEARANCE_DEFAULTS = {
    "newspaper_name": "The Daily Digest",
    "theme": "traditional",
    "font_size": 9,
    "paper_size": "A5",
    "columns": 1,
}


def _load_appearance() -> dict:
    """Load appearance settings from config/appearance.yml, falling back to env vars."""
    base = {
        "newspaper_name": os.environ.get("NEWSPAPER_NAME", _APPEARANCE_DEFAULTS["newspaper_name"]),
        "theme": os.environ.get("PDF_THEME", _APPEARANCE_DEFAULTS["theme"]),
        "font_size": int(os.environ.get("PDF_FONT_SIZE", _APPEARANCE_DEFAULTS["font_size"])),
        "paper_size": os.environ.get("PDF_PAPER_SIZE", _APPEARANCE_DEFAULTS["paper_size"]),
        "columns": int(os.environ.get("PDF_COLUMNS", _APPEARANCE_DEFAULTS["columns"])),
    }
    path = Path("/app/config/appearance.yml")
    if path.exists():
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            base.update({k: v for k, v in data.items() if k in base})
        except Exception as exc:
            logger.warning("Could not read appearance.yml: %s", exc)
    return base


def collect() -> dict:
    """Run all enabled sources and return structured newspaper context."""
    from app.sources import weather, rss, email_source, ticktick, learning, shell

    blocks: list[dict] = []

    for source_module in [weather, ticktick, email_source, rss, learning, shell]:
        try:
            fetched = source_module.fetch()
            blocks.extend(fetched)
        except Exception as exc:
            logger.error("Source %s failed: %s", source_module.__name__, exc)

    if os.environ.get("AI_SUMMARY_ENABLED", "false").lower() == "true":
        blocks = _ai_summarise(blocks)

    # Split into typed groups for the template
    weather_blocks = [b for b in blocks if b["type"] == "weather"]
    task_blocks    = [b for b in blocks if b["type"] == "task"]
    email_blocks   = [b for b in blocks if b["type"] == "email"]
    article_blocks = [b for b in blocks if b["type"] == "article"]
    lesson_blocks  = [b for b in blocks if b["type"] == "lesson"]
    shell_blocks   = [b for b in blocks if b["type"] == "shell"]

    # Group articles by source feed
    feeds: dict[str, list[dict]] = {}
    for article in article_blocks:
        feeds.setdefault(article["source"], []).append(article)

    now = datetime.now()
    return {
        "generated_at": now.strftime("%A, %d %B %Y"),
        "generated_time": now.strftime("%H:%M"),
        "weather": weather_blocks[0] if weather_blocks else None,
        "tasks": task_blocks,
        "emails": email_blocks,
        "feeds": feeds,
        "lessons": lesson_blocks,
        "shell_outputs": shell_blocks,
        "all_blocks": blocks,
        "config": _load_appearance(),
    }


def _ai_summarise(blocks: list[dict]) -> list[dict]:
    """Replace article bodies with AI-generated summaries."""
    api_key = os.environ.get("AI_API_KEY", "")
    base_url = os.environ.get("AI_API_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")
    max_tokens = int(os.environ.get("AI_SUMMARY_MAX_TOKENS", "120"))

    if not api_key:
        logger.warning("AI_SUMMARY_ENABLED but AI_API_KEY not set — skipping")
        return blocks

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
    except Exception as exc:
        logger.error("OpenAI client init failed: %s", exc)
        return blocks

    for block in blocks:
        if block["type"] != "article" or not block.get("body"):
            continue
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Summarise this news article in 2-3 concise sentences for a morning briefing.\n\n"
                        f"Title: {block['title']}\n\n{block['body']}"
                    ),
                }],
            )
            block["body"] = response.choices[0].message.content.strip()
            block["ai_summarised"] = True
        except Exception as exc:
            logger.warning("AI summary failed for '%s': %s", block["title"], exc)

    return blocks
