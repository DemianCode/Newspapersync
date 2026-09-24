"""Email source — connects via IMAP and fetches recent unread messages.

Shows: sender, subject, short snippet. Full body is intentionally omitted
to keep the newspaper concise.
"""

from __future__ import annotations

import logging
import os
import re

from imap_tools import MailBox, AND

from app import config_loader as cfg
from app.sources._text import html_to_text, truncate, when

logger = logging.getLogger(__name__)


def fetch() -> list[dict]:
    if cfg.get("EMAIL_ENABLED", "false").lower() != "true":
        return []

    host = cfg.get("EMAIL_IMAP_HOST", "")
    port = int(cfg.get("EMAIL_IMAP_PORT", "993"))
    username = os.environ.get("EMAIL_USERNAME", "")   # secret — .env only
    password = os.environ.get("EMAIL_PASSWORD", "")   # secret — .env only
    max_items = int(cfg.get("EMAIL_MAX_ITEMS", "10"))

    if not host or not username or not password:
        logger.warning("Email source enabled but credentials not set")
        return []

    items: list[dict] = []
    try:
        with MailBox(host, port).login(username, password) as mailbox:
            # mark_seen=False: imap-tools marks fetched messages as read by
            # default, which would silently clear the inbox every morning.
            msgs = list(mailbox.fetch(AND(seen=False), limit=max_items, reverse=True, mark_seen=False))
            for msg in msgs:
                items.append({
                    "type": "email",
                    "source": "Email",
                    "title": msg.subject.strip() or "(no subject)",
                    "body": _snippet(msg.text or msg.html or ""),
                    "published": when(msg.date) if msg.date and msg.date.year > 1900 else "",
                    "meta": {
                        "from": _sender(msg),
                        "address": msg.from_,
                        "unread_total": None,  # populated below
                    },
                })
            # Attach total unread count as meta on the first item
            total_unread = mailbox.folder.status("INBOX").get("UNSEEN", len(items))
            if items:
                items[0]["meta"]["unread_total"] = total_unread
    except Exception as exc:
        logger.error("Email fetch failed: %s", exc)
        return []

    return items


def _sender(msg) -> str:
    """Display name when the message has one ("Alex Morgan"), else the address."""
    values = getattr(msg, "from_values", None)
    name = (getattr(values, "name", "") or "").strip().strip('"')
    return name or msg.from_ or "Unknown sender"


def _snippet(text: str, length: int = 180) -> str:
    # Quoted replies and signatures add nothing to a morning glance.
    text = re.split(r"\n\s*(?:On .{0,120}wrote:|-- ?\n|>)", text, maxsplit=1)[0]
    return truncate(html_to_text(text), length)
