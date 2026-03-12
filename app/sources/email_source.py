"""Email source — connects via IMAP and fetches recent unread messages.

Shows: sender, subject, short snippet. Full body is intentionally omitted
to keep the newspaper concise.
"""

from __future__ import annotations

import logging
import os

from imap_tools import MailBox, AND

logger = logging.getLogger(__name__)


def fetch() -> list[dict]:
    if os.environ.get("EMAIL_ENABLED", "false").lower() != "true":
        return []

    host = os.environ.get("EMAIL_IMAP_HOST", "")
    port = int(os.environ.get("EMAIL_IMAP_PORT", "993"))
    username = os.environ.get("EMAIL_USERNAME", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    max_items = int(os.environ.get("EMAIL_MAX_ITEMS", "10"))

    if not host or not username or not password:
        logger.warning("Email source enabled but credentials not set")
        return []

    items: list[dict] = []
    try:
        with MailBox(host, port).login(username, password) as mailbox:
            msgs = list(mailbox.fetch(AND(seen=False), limit=max_items, reverse=True))
            for msg in msgs:
                snippet = _snippet(msg.text or msg.html or "")
                items.append({
                    "type": "email",
                    "source": "Email",
                    "title": msg.subject or "(no subject)",
                    "body": snippet,
                    "published": msg.date.strftime("%d %b %Y, %H:%M") if msg.date else "",
                    "meta": {
                        "from": msg.from_,
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


def _snippet(text: str, length: int = 160) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > length:
        text = text[:length].rsplit(" ", 1)[0] + "…"
    return text
