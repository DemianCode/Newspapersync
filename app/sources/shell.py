"""Shell snippet source — runs user-defined commands and includes output in the newspaper.

Commands are stored in config/shell_snippets.yml.
Output is ANSI-stripped and truncated for PDF safety.

Security note: this tool runs on a local self-hosted server. Commands are run with
shell=True so pipes and redirects work. An obvious blocklist guards against
accidental destructive commands; the "Test" button in the UI lets you preview
output before it ever appears in a PDF.
"""

from __future__ import annotations

import logging
import re
import subprocess
import uuid
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path("/app/config/shell_snippets.yml")
_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_MAX_OUTPUT_CHARS = 3000
_MAX_COMMAND_CHARS = 2000
_DEFAULT_TIMEOUT = 10

# Guard against obviously destructive commands. Local-only tool but still worth
# catching accidental pastes.
_BLOCKED_RE = re.compile(
    r"\brm\s+-[rRf]{1,3}f?\b"
    r"|\bmkfs\b"
    r"|\bdd\s+if="
    r"|\bchmod\s+[0-7]*777\b"
    r"|\b:()\{.*\};"  # fork bomb
    r"|>\s*/dev/[hs]d[a-z]",
    re.IGNORECASE,
)


def fetch() -> list[dict]:
    """Run all active shell snippets and return output blocks."""
    config = _load_config()
    blocks: list[dict] = []

    for snippet in config.get("snippets", []):
        if not snippet.get("active", True):
            continue

        name = snippet.get("name", "Shell")
        command = snippet.get("command", "").strip()
        timeout = int(snippet.get("timeout", _DEFAULT_TIMEOUT))

        if not command:
            continue

        output, error = _run_command(command, timeout)

        if error:
            logger.warning("Shell snippet '%s' error: %s", name, error)

        blocks.append({
            "type": "shell",
            "title": name,
            "body": f"[Error: {error}]" if (error and not output) else output,
            "source": "Shell",
            "published": None,
            "meta": {
                "snippet_id": snippet["id"],
                "command": command,
                "error": error,
            },
        })

    return blocks


def run_test(command: str, timeout: int = _DEFAULT_TIMEOUT) -> tuple[str, str | None]:
    """Run a command for UI preview. Returns (output, error_or_None)."""
    return _run_command(command, timeout)


# ── CRUD helpers (used by web routes) ────────────────────────────────────────

def get_snippets() -> list[dict]:
    return _load_config().get("snippets", [])


def add_snippet(name: str, command: str, timeout: int = _DEFAULT_TIMEOUT) -> dict:
    config = _load_config()
    snippet = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "command": command,
        "active": True,
        "timeout": timeout,
    }
    config.setdefault("snippets", []).append(snippet)
    _save_config(config)
    return snippet


def update_snippet(snippet_id: str, **kwargs) -> bool:
    config = _load_config()
    for s in config.get("snippets", []):
        if s["id"] == snippet_id:
            for key in ("name", "command", "active", "timeout"):
                if key in kwargs:
                    s[key] = kwargs[key]
            _save_config(config)
            return True
    return False


def delete_snippet(snippet_id: str) -> bool:
    config = _load_config()
    snippets = config.get("snippets", [])
    new_snippets = [s for s in snippets if s["id"] != snippet_id]
    if len(new_snippets) == len(snippets):
        return False
    config["snippets"] = new_snippets
    _save_config(config)
    return True


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_command(command: str, timeout: int) -> tuple[str, str | None]:
    if len(command) > _MAX_COMMAND_CHARS:
        return "", f"Command exceeds {_MAX_COMMAND_CHARS}-character limit"
    if _BLOCKED_RE.search(command):
        return "", "Command blocked by safety filter"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = _clean(result.stdout)
        if result.returncode != 0:
            stderr = _clean(result.stderr)
            err_msg = f"Exit {result.returncode}" + (f": {stderr[:300]}" if stderr else "")
            return output, err_msg
        return output, None
    except subprocess.TimeoutExpired:
        return "", f"Timed out after {timeout}s"
    except Exception as exc:
        return "", str(exc)


def _clean(text: str) -> str:
    """Strip ANSI escape codes and non-printable control characters, then truncate."""
    text = _ANSI_ESCAPE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    text = text.strip()
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[:_MAX_OUTPUT_CHARS] + f"\n[... truncated at {_MAX_OUTPUT_CHARS} chars]"
    return text


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {"snippets": []}
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {"snippets": []}


def _save_config(config: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
