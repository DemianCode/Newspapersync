"""Base class for all job scrapers."""

from __future__ import annotations


class BaseJobScraper:
    """Abstract base for job scrapers.

    Each subclass implements search() and returns a list of raw job dicts
    with a consistent shape consumed by app/sources/jobs.py.
    """

    def search(self, config: dict) -> list[dict]:
        """Fetch jobs matching the search config and return raw job dicts.

        Raw job dict shape:
            id          — unique stable identifier (e.g. "seek-12345678")
            title       — job title string
            company     — employer / advertiser name
            location    — location string (e.g. "Melbourne VIC 3000")
            salary      — raw salary string, may be empty
            description — short description / teaser
            url         — direct link to the job posting
            date_posted — date string, may be empty
            source_name — human-readable source label (e.g. "Seek", "RMIT")
        """
        raise NotImplementedError
