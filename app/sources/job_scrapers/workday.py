"""Workday job board scraper.

Uses Workday's undocumented public JSON API — no JavaScript rendering needed.
Works for any Workday-hosted careers site including:
  - RMIT:              tenant=rmit,   instance=wd3,   path=RMIT_Careers
  - University of Melbourne: tenant=unimelb, instance=wd105, path=UoM_External_Career

To add another Workday institution, simply configure:
  source: workday
  workday_tenant: <tenant>      # subdomain before .wd*.myworkdayjobs.com
  workday_instance: <instance>  # e.g. wd3, wd105
  workday_path: <path>          # career site path segment
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime

import requests

from app.sources.job_scrapers.base import BaseJobScraper

logger = logging.getLogger(__name__)

_TIMEOUT = 15
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
}


class WorkdayScraper(BaseJobScraper):
    def search(self, config: dict) -> list[dict]:
        tenant = config.get("workday_tenant", "")
        instance = config.get("workday_instance", "")
        path = config.get("workday_path", "")
        keywords = config.get("keywords", "")
        max_results = int(config.get("max_results", 20))
        source_name = config.get("name", f"Workday ({tenant})")

        if not all([tenant, instance, path]):
            logger.warning(
                "Workday search '%s' missing workday_tenant/instance/path", source_name
            )
            return []

        endpoint = (
            f"https://{tenant}.{instance}.myworkdayjobs.com"
            f"/wday/cxs/{tenant}/{path}/jobs"
        )
        base_url = f"https://{tenant}.{instance}.myworkdayjobs.com/{path}"

        payload = {
            "limit": max_results,
            "offset": 0,
            "searchText": keywords,
            "appliedFacets": {},
        }

        try:
            resp = requests.post(
                endpoint, json=payload, headers=_HEADERS, timeout=_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Workday API request failed for %s: %s", source_name, exc)
            return []

        postings = data.get("jobPostings", [])
        results = []
        for p in postings:
            title = p.get("title", "")
            external_path = p.get("externalPath", "")
            if not title or not external_path:
                continue

            job_url = base_url + external_path
            job_id = "workday-" + tenant + "-" + hashlib.md5(external_path.encode()).hexdigest()[:10]

            location = p.get("locationsText", "") or ""
            posted_on = p.get("postedOn", "") or ""
            # bulletFields contains brief description points
            bullets = p.get("bulletFields", []) or []
            description = " | ".join(str(b) for b in bullets if b)

            results.append({
                "id": job_id,
                "title": title,
                "company": source_name,
                "location": location,
                "salary": "",  # Workday API rarely exposes salary
                "description": description[:400],
                "url": job_url,
                "date_posted": _parse_workday_date(posted_on),
                "source_name": source_name,
            })

        logger.info("Workday (%s): fetched %d jobs", source_name, len(results))
        return results


def _parse_workday_date(raw: str) -> str:
    """Parse Workday date strings like 'Posted 30+ Days Ago' or '2024-01-15'."""
    if not raw:
        return ""
    # ISO date
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d %b %Y")
        except ValueError:
            pass
    # Human-readable Workday strings e.g. "Posted 2 Days Ago"
    return raw
