"""Aggregator — collects content from all enabled sources.

Optionally runs AI summarisation if configured.
Returns a structured context dict consumed by the PDF builder.

When an edition dict is provided, its 'sources' config controls which sources
run. When edition is None, each source reads its own enable flag from global
settings (backwards-compatible behaviour).
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


def _pick_block(blocks: list[dict], type_name: str, source_name: str) -> dict | None:
    """Return the first block of type_name, or a source_error for source_name, or None."""
    for b in blocks:
        if b["type"] == type_name:
            return b
    for b in blocks:
        if b["type"] == "source_error" and b.get("source") == source_name:
            return b
    return None


def collect(edition: dict | None = None) -> dict:
    """Run enabled sources and return structured newspaper context.

    When edition is provided, its 'sources' dict controls which sources run.
    When edition is None, each source reads its own enable flag from global
    settings (env vars / settings.yml).
    """
    from app.sources import (
        weather, rss, email_source, ticktick, learning, shell, sudoku,
        wikipedia, wikiquote_daily, word_of_the_day,
    )

    edition_sources = edition.get("sources") if edition else None

    def should_run(key: str) -> bool:
        """When an edition is active, it controls which sources run.
        Without an edition, all modules run and each checks its own enable flag."""
        if edition_sources is not None:
            return bool(edition_sources.get(key, False))
        return True  # no edition — let each source handle its own flag

    # (source_key, module) pairs in render order
    source_map = [
        ("weather",         weather),
        ("tasks",           ticktick),
        ("email_inbox",     email_source),
        ("news",            rss),
        ("learning",        learning),
        ("shell",           shell),
        ("sudoku",          sudoku),
        ("wikipedia",       wikipedia),
        ("wikiquote",       wikiquote_daily),
        ("word_of_the_day", word_of_the_day),
    ]

    blocks: list[dict] = []
    for key, module in source_map:
        if should_run(key):
            try:
                fetched = module.fetch()
                blocks.extend(fetched)
            except Exception as exc:
                logger.error("Source %s failed: %s", module.__name__, exc)

    if os.environ.get("AI_SUMMARY_ENABLED", "false").lower() == "true":
        blocks = _ai_summarise(blocks)

    # Split into typed groups for the template
    weather_blocks  = [b for b in blocks if b["type"] == "weather"]
    task_blocks     = [b for b in blocks if b["type"] == "task"]
    email_blocks    = [b for b in blocks if b["type"] == "email"]
    article_blocks  = [b for b in blocks if b["type"] == "article"]
    lesson_blocks   = [b for b in blocks if b["type"] == "lesson"]
    shell_blocks    = [b for b in blocks if b["type"] == "shell"]
    sudoku_blocks   = [b for b in blocks if b["type"] == "sudoku"]

    # Group articles by source feed
    feeds: dict[str, list[dict]] = {}
    for article in article_blocks:
        feeds.setdefault(article["source"], []).append(article)

    # Appearance: start from global, then apply edition overrides
    config = _load_appearance()
    if edition and "appearance" in edition:
        allowed = {"theme", "paper_size", "columns", "font_size"}
        config.update({k: v for k, v in edition["appearance"].items() if k in allowed})

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
        "sudoku": sudoku_blocks[0] if sudoku_blocks else None,
        "wikipedia": _pick_block(blocks, "wikipedia", "wikipedia"),
        "wikiquote": _pick_block(blocks, "wikiquote", "wikiquote_daily"),
        "word_of_the_day": _pick_block(blocks, "word_of_the_day", "word_of_the_day"),
        "edition_name": edition.get("name") if edition else None,
        "all_blocks": blocks,
        "config": config,
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
