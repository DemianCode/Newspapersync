"""Config loader — settings.yml overrides env vars.

Priority (highest first):
  1. config/settings.yml  — written by the web UI
  2. os.environ           — docker-compose.yml / .env

Read fresh on every call so web-saved changes take effect on the next
pipeline run without a container restart.

Secrets (passwords, API keys) are intentionally NOT in settings.yml;
they stay in .env and are read directly via os.environ by the sources
that need them.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path("/app/config/settings.yml")

# Keys that must never be stored in settings.yml (handled via .env only)
_SECRET_KEYS = frozenset({
    "EMAIL_USERNAME", "EMAIL_PASSWORD",
    "TICKTICK_CLIENT_ID", "TICKTICK_CLIENT_SECRET",
    "AI_API_KEY",
    "REMARKABLE_DEVICE_EMAIL",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
})


def get(key: str, default: str = "") -> str:
    """Return the effective value for *key*, preferring settings.yml over env."""
    if key in _SECRET_KEYS:
        return os.environ.get(key, default)
    try:
        if _SETTINGS_PATH.exists():
            with open(_SETTINGS_PATH) as f:
                data = yaml.safe_load(f) or {}
            if key in data and data[key] is not None:
                return str(data[key])
    except Exception as exc:
        logger.warning("config_loader: could not read settings.yml: %s", exc)
    return os.environ.get(key, default)


def load_all() -> dict:
    """Return the full settings.yml dict (only overrides, not merged with env)."""
    try:
        if _SETTINGS_PATH.exists():
            with open(_SETTINGS_PATH) as f:
                return yaml.safe_load(f) or {}
    except Exception as exc:
        logger.warning("config_loader: could not read settings.yml: %s", exc)
    return {}


def save(updates: dict) -> None:
    """Merge *updates* into settings.yml, excluding secret keys."""
    safe = {k: v for k, v in updates.items() if k not in _SECRET_KEYS}
    current = load_all()
    current.update(safe)
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SETTINGS_PATH, "w") as f:
        yaml.dump(current, f, default_flow_style=False, allow_unicode=True, sort_keys=True)
