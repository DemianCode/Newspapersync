"""reMarkable sync via rmapi.

Uploads today's PDF, archives yesterday's, and optionally prunes old archives.

rmapi commands used:
  rmapi ls <folder>        — list contents
  rmapi mkdir <folder>     — create folder (no-op if exists)
  rmapi put <file> <folder>— upload file
  rmapi rm <path>          — delete a document
  rmapi mv <src> <dst>     — move a document
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_REMARKABLE_FOLDER = os.environ.get("REMARKABLE_FOLDER", "Newspaper")
_ARCHIVE_FOLDER = os.environ.get("REMARKABLE_ARCHIVE_FOLDER", "Newspaper/Archive")
_KEEP_DAYS = int(os.environ.get("REMARKABLE_ARCHIVE_KEEP_DAYS", "30"))
_DATE_PATTERN = re.compile(r"newspaper-(\d{4}-\d{2}-\d{2})")


def sync(pdf_path: Path) -> bool:
    """Upload today's PDF and manage archives. Returns True on success."""
    if not _rmapi_available():
        logger.error("rmapi not found in PATH. Is it installed in the container?")
        return False

    _ensure_folder(_REMARKABLE_FOLDER)
    if _ARCHIVE_FOLDER:
        _ensure_folder(_ARCHIVE_FOLDER)
        _archive_previous()
        if _KEEP_DAYS > 0:
            _prune_archive()

    return _upload(pdf_path)


# ── rmapi helpers ──────────────────────────────────────────────────────────────

def _run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["rmapi"] + args
    logger.debug("rmapi: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if check and result.returncode != 0:
        raise RuntimeError(f"rmapi {args[0]} failed: {result.stderr.strip()}")
    return result


def _rmapi_available() -> bool:
    try:
        subprocess.run(["rmapi", "version"], capture_output=True, timeout=5)
        return True
    except FileNotFoundError:
        return False


def _ensure_folder(folder: str) -> None:
    try:
        _run(["mkdir", folder], check=False)
    except Exception as exc:
        logger.debug("mkdir %s: %s", folder, exc)


def _list_folder(folder: str) -> list[str]:
    """Return document names in a reMarkable folder."""
    try:
        result = _run(["ls", folder], check=False)
        lines = result.stdout.strip().splitlines()
        # rmapi ls output: "[d] FolderName" or "[f] DocumentName"
        names = []
        for line in lines:
            line = line.strip()
            if line.startswith("[f]"):
                names.append(line[3:].strip())
        return names
    except Exception as exc:
        logger.warning("ls %s failed: %s", folder, exc)
        return []


def _archive_previous() -> None:
    """Move any newspaper PDFs in the main folder to the archive folder."""
    docs = _list_folder(_REMARKABLE_FOLDER)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    for doc in docs:
        m = _DATE_PATTERN.search(doc)
        if m and m.group(1) != today:
            src = f"{_REMARKABLE_FOLDER}/{doc}"
            try:
                _run(["mv", src, _ARCHIVE_FOLDER])
                logger.info("Archived: %s → %s", src, _ARCHIVE_FOLDER)
            except Exception as exc:
                logger.warning("Could not archive %s: %s", src, exc)


def _prune_archive() -> None:
    """Delete archived PDFs older than REMARKABLE_ARCHIVE_KEEP_DAYS."""
    if not _ARCHIVE_FOLDER:
        return

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_KEEP_DAYS)
    docs = _list_folder(_ARCHIVE_FOLDER)

    for doc in docs:
        m = _DATE_PATTERN.search(doc)
        if m:
            try:
                doc_date = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if doc_date < cutoff:
                    _run(["rm", f"{_ARCHIVE_FOLDER}/{doc}"])
                    logger.info("Pruned old archive: %s", doc)
            except Exception as exc:
                logger.warning("Could not prune %s: %s", doc, exc)


def _upload(pdf_path: Path) -> bool:
    try:
        _run(["put", str(pdf_path), _REMARKABLE_FOLDER])
        logger.info("Uploaded %s to reMarkable/%s", pdf_path.name, _REMARKABLE_FOLDER)
        return True
    except Exception as exc:
        logger.error("Upload failed: %s", exc)
        return False
