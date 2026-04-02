"""reMarkable sync — supports three delivery methods.

REMARKABLE_SYNC_METHOD (set in docker-compose.yml):
  rmapi                    — rmapi CLI only (supports folder archiving)
  email                    — SMTP to <device>@mail.remarkable.com (no archiving)
  rmapi_with_email_fallback — try rmapi first; on failure, fall back to email

Secrets (set in .env):
  REMARKABLE_DEVICE_EMAIL  — your device's @mail.remarkable.com address
  SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD — outbound mailer

rmapi commands used:
  rmapi ls <folder>         — list folder contents
  rmapi mkdir <folder>      — create folder (no-op if exists)
  rmapi put <file> <folder> — upload file
  rmapi rm <path>           — delete document
  rmapi mv <src> <dst>      — move document
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
import subprocess
from datetime import datetime, timedelta, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

_METHOD = os.environ.get("REMARKABLE_SYNC_METHOD", "rmapi_with_email_fallback").lower()
_REMARKABLE_FOLDER = os.environ.get("REMARKABLE_FOLDER", "Newspaper")
_ARCHIVE_FOLDER = os.environ.get("REMARKABLE_ARCHIVE_FOLDER", "Newspaper/Archive")
_KEEP_DAYS = int(os.environ.get("REMARKABLE_ARCHIVE_KEEP_DAYS", "30"))
_DATE_PATTERN = re.compile(r"newspaper-(\d{4}-\d{2}-\d{2})")


def sync(pdf_path: Path) -> bool:
    """Deliver today's PDF to reMarkable using the configured method."""
    if _METHOD == "rmapi":
        return _sync_rmapi(pdf_path)
    elif _METHOD == "email":
        return _sync_email(pdf_path)
    elif _METHOD == "rmapi_with_email_fallback":
        logger.info("Attempting rmapi sync…")
        if _sync_rmapi(pdf_path):
            return True
        logger.warning("rmapi sync failed — falling back to email delivery")
        return _sync_email(pdf_path)
    else:
        logger.error("Unknown REMARKABLE_SYNC_METHOD '%s'. Use: rmapi | email | rmapi_with_email_fallback", _METHOD)
        return False


# ── rmapi delivery ─────────────────────────────────────────────────────────────

def _sync_rmapi(pdf_path: Path) -> bool:
    """Upload via rmapi with archive management. Returns True on success."""
    if not _rmapi_available():
        logger.error(
            "rmapi not found or not authenticated. "
            "Run: docker compose run --rm newspapersync rmapi"
        )
        return False

    _ensure_folder(_REMARKABLE_FOLDER)

    if _ARCHIVE_FOLDER:
        _ensure_folder(_ARCHIVE_FOLDER)
        _archive_previous()
        if _KEEP_DAYS > 0:
            _prune_archive()

    # Skip upload if this PDF is already in the folder (idempotent re-sync).
    # rmapi errors on duplicate puts; checking first makes manual re-sync safe.
    existing = _list_folder(_REMARKABLE_FOLDER)
    if pdf_path.stem in existing:
        logger.info("'%s' already on reMarkable — skipping upload", pdf_path.stem)
        return True

    return _rmapi_upload(pdf_path)


def _rmapi_run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    # -ni = non-interactive: fail cleanly if not authenticated instead of prompting.
    # This prevents the "Code has the wrong length" errors when running headlessly.
    cmd = ["rmapi", "-ni"] + args
    logger.debug("rmapi: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if check and result.returncode != 0:
        raise RuntimeError(f"rmapi {args[0]} failed: {result.stderr.strip()}")
    return result


def _rmapi_available() -> bool:
    try:
        result = subprocess.run(["rmapi", "version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            return False
    except FileNotFoundError:
        return False

    # Verify authenticated by doing a live non-interactive test.
    # Checking for a specific token filename is fragile (the name varies by rmapi version);
    # running `rmapi -ni ls /` is the only reliable way to confirm auth state.
    auth_dir = Path("/root/.local/share/rmapi")
    token_files = list(auth_dir.glob("*")) if auth_dir.exists() else []
    logger.debug("rmapi config dir contents: %s", [f.name for f in token_files])

    try:
        result = subprocess.run(
            ["rmapi", "-ni", "ls", "/"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        logger.error(
            "rmapi -ni ls / timed out after 15 s — reMarkable cloud unreachable or network issue. "
            "Sync will be skipped this run."
        )
        return False
    if result.returncode != 0:
        logger.error(
            "rmapi is installed but not authenticated (rmapi -ni ls / returned %d: %s). "
            "Authenticate once with: docker compose run --rm -it newspapersync rmapi",
            result.returncode, result.stderr.strip(),
        )
        return False
    return True


def _ensure_folder(folder: str) -> None:
    try:
        _rmapi_run(["mkdir", folder], check=False)
    except Exception as exc:
        logger.debug("mkdir %s: %s", folder, exc)


def _list_folder(folder: str) -> list[str]:
    try:
        result = _rmapi_run(["ls", folder], check=False)
        names = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("[f]"):
                names.append(line[3:].strip())
        return names
    except Exception as exc:
        logger.warning("ls %s failed: %s", folder, exc)
        return []


def _archive_previous() -> None:
    """Move prior newspaper PDFs from the main folder into the archive folder."""
    docs = _list_folder(_REMARKABLE_FOLDER)
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    for doc in docs:
        m = _DATE_PATTERN.search(doc)
        if m and m.group(1) != today:
            src = f"{_REMARKABLE_FOLDER}/{doc}"
            try:
                _rmapi_run(["mv", src, _ARCHIVE_FOLDER])
                logger.info("Archived: %s → %s", src, _ARCHIVE_FOLDER)
            except Exception as exc:
                logger.warning("Could not archive %s: %s", src, exc)


def _prune_archive() -> None:
    """Delete archive entries older than REMARKABLE_ARCHIVE_KEEP_DAYS."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_KEEP_DAYS)
    for doc in _list_folder(_ARCHIVE_FOLDER):
        m = _DATE_PATTERN.search(doc)
        if m:
            try:
                doc_date = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if doc_date < cutoff:
                    _rmapi_run(["rm", f"{_ARCHIVE_FOLDER}/{doc}"])
                    logger.info("Pruned old archive: %s", doc)
            except Exception as exc:
                logger.warning("Could not prune %s: %s", doc, exc)


def _rmapi_upload(pdf_path: Path) -> bool:
    try:
        _rmapi_run(["put", str(pdf_path), _REMARKABLE_FOLDER])
        logger.info("Uploaded %s to reMarkable/%s", pdf_path.name, _REMARKABLE_FOLDER)
        return True
    except Exception as exc:
        logger.error("rmapi upload failed: %s", exc)
        return False


# ── Email delivery ─────────────────────────────────────────────────────────────

def _smtp_send(pdf_path: Path, recipients: list[str], subject: str) -> None:
    """Core SMTP send — attach the PDF and send to the given recipients.

    Reads SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD from env.
    Raises on missing credentials or SMTP failure (caller decides how to handle).
    """
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USERNAME", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")

    missing = [k for k, v in {
        "SMTP_HOST": smtp_host,
        "SMTP_USERNAME": smtp_user,
        "SMTP_PASSWORD": smtp_pass,
    }.items() if not v]
    if missing:
        raise ValueError(f"Missing SMTP credentials in .env: {', '.join(missing)}")

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText("Your daily newspaper is attached.", "plain"))

    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        msg.attach(attachment)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, recipients, msg.as_string())


def send_pdf_copy(pdf_path: Path) -> None:
    """If PDF_EMAIL_ENABLED, email the PDF to PDF_EMAIL_RECIPIENT(s).

    Controlled by PDF_EMAIL_ENABLED / PDF_EMAIL_RECIPIENT in docker-compose.yml
    or settings. SMTP credentials come from .env.
    """
    if os.environ.get("PDF_EMAIL_ENABLED", "false").lower() != "true":
        return
    _send_to_configured_recipients(pdf_path, label="PDF email copy")


def force_email_send(pdf_path: Path) -> None:
    """Send the PDF to PDF_EMAIL_RECIPIENT unconditionally.

    Used by edition delivery when delivery.email = true, bypassing the
    PDF_EMAIL_ENABLED flag. Reads PDF_EMAIL_RECIPIENT from settings.
    """
    _send_to_configured_recipients(pdf_path, label="Edition email delivery")


def _send_to_configured_recipients(pdf_path: Path, label: str = "Email") -> None:
    """Read PDF_EMAIL_RECIPIENT from env/settings and send the PDF."""
    try:
        from app import config_loader
        recipients_raw = config_loader.get("PDF_EMAIL_RECIPIENT", os.environ.get("PDF_EMAIL_RECIPIENT", ""))
    except Exception:
        recipients_raw = os.environ.get("PDF_EMAIL_RECIPIENT", "")

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    if not recipients:
        logger.error("%s: PDF_EMAIL_RECIPIENT is not set", label)
        return

    subject = f"Your Daily Newspaper — {datetime.now(tz=timezone.utc).strftime('%d %B %Y')}"
    try:
        _smtp_send(pdf_path, recipients, subject)
        logger.info("%s sent to: %s", label, ", ".join(recipients))
    except Exception as exc:
        logger.error("%s failed: %s", label, exc)


def _sync_email(pdf_path: Path) -> bool:
    """Send PDF as attachment to the reMarkable device email address."""
    device_email = os.environ.get("REMARKABLE_DEVICE_EMAIL", "")
    if not device_email:
        logger.error("Email sync: REMARKABLE_DEVICE_EMAIL is not set in .env")
        return False

    subject = f"Daily Newspaper — {datetime.now(tz=timezone.utc).strftime('%d %B %Y')}"
    try:
        _smtp_send(pdf_path, [device_email], subject)
        logger.info("Emailed %s to reMarkable device (%s)", pdf_path.name, device_email)
        return True
    except Exception as exc:
        logger.error("Email delivery to reMarkable failed: %s", exc)
        return False
