"""Seek.com.au job scraper.

Primary method: undocumented Seek JSON search API.
Fallback: BeautifulSoup HTML scrape of the search results page.
"""

from __future__ import annotations

import hashlib
import logging
import re

import requests

from app.sources.job_scrapers.base import BaseJobScraper

logger = logging.getLogger(__name__)

_API_URL = "https://www.seek.com.au/api/chalice-search/v4/search"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.seek.com.au/",
    "X-Seek-Site": "Chalice",
}
_TIMEOUT = 15


class SeekScraper(BaseJobScraper):
    def search(self, config: dict) -> list[dict]:
        keywords = config.get("keywords", "")
        location = config.get("location", "")
        max_results = int(config.get("max_results", 20))
        source_name = config.get("name", "Seek")

        jobs = self._api_search(keywords, location, max_results, source_name)
        if not jobs:
            logger.info("Seek API returned no results, trying HTML fallback")
            jobs = self._html_search(keywords, location, max_results, source_name)
        return jobs

    # ── JSON API ─────────────────────────────────────────────────────────────

    def _api_search(
        self, keywords: str, location: str, max_results: int, source_name: str
    ) -> list[dict]:
        params = {
            "siteKey": "AU-Main",
            "sourcesystem": "houston",
            "keywords": keywords,
            "where": location,
            "page": 1,
            "pageSize": max_results,
            "include": "seodata",
            "locale": "en-AU",
        }
        try:
            resp = requests.get(_API_URL, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("Seek API request failed: %s", exc)
            return []

        raw_jobs = data.get("data", {}).get("jobs", [])
        results = []
        for j in raw_jobs:
            job_id = str(j.get("id", ""))
            title = j.get("title", "")
            company = j.get("advertiser", {}).get("description", "")
            locations = j.get("locations", [])
            loc_label = locations[0].get("label", "") if locations else ""
            salary = j.get("salary", "") or ""
            teaser = j.get("teaser", "") or ""
            listing_date = j.get("listingDate", "") or ""
            url = f"https://www.seek.com.au/job/{job_id}" if job_id else ""

            if not title or not url:
                continue

            results.append({
                "id": f"seek-{job_id}",
                "title": title,
                "company": company,
                "location": loc_label,
                "salary": salary,
                "description": teaser,
                "url": url,
                "date_posted": _parse_seek_date(listing_date),
                "source_name": source_name,
            })
        return results

    # ── HTML fallback ─────────────────────────────────────────────────────────

    def _html_search(
        self, keywords: str, location: str, max_results: int, source_name: str
    ) -> list[dict]:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 not installed — cannot use Seek HTML fallback")
            return []

        slug_kw = re.sub(r"[^a-z0-9]+", "-", keywords.lower()).strip("-")
        slug_loc = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")
        url = f"https://www.seek.com.au/{slug_kw}-jobs/in-{slug_loc}" if slug_loc else f"https://www.seek.com.au/{slug_kw}-jobs"

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Seek HTML fallback request failed: %s", exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        results = []

        for card in soup.select('article[data-card-type="JobCard"]')[:max_results]:
            title_el = card.select_one('[data-automation="job-list-view-job-title"]')
            company_el = card.select_one('[data-automation="job-list-view-job-advertiser"]')
            loc_el = card.select_one('[data-automation="job-list-view-job-location"]')
            salary_el = card.select_one('[data-automation="job-details-salary"]')
            teaser_el = card.select_one('[data-automation="job-list-view-job-description"]')
            link_el = card.select_one('a[data-automation="job-list-view-job-link"]')

            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            href = link_el["href"] if link_el and link_el.get("href") else ""
            job_url = f"https://www.seek.com.au{href}" if href.startswith("/") else href
            job_id = hashlib.md5(job_url.encode()).hexdigest()[:12]

            results.append({
                "id": f"seek-{job_id}",
                "title": title,
                "company": company_el.get_text(strip=True) if company_el else "",
                "location": loc_el.get_text(strip=True) if loc_el else "",
                "salary": salary_el.get_text(strip=True) if salary_el else "",
                "description": teaser_el.get_text(strip=True) if teaser_el else "",
                "url": job_url,
                "date_posted": "",
                "source_name": source_name,
            })

        return results


def _parse_seek_date(raw: str) -> str:
    """Convert ISO-ish date string to a readable format."""
    if not raw:
        return ""
    # raw is typically "2024-01-15T10:30:00Z" or "2024-01-15"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        from datetime import datetime
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%d %b %Y")
        except ValueError:
            pass
    return raw
