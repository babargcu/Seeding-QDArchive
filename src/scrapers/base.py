"""
Abstract base scraper — all source-specific scrapers inherit from this.
"""

import time
import logging
from abc import ABC, abstractmethod

import requests

import config
from src.license_checker import is_open, classify

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Fetch metadata records from a single source."""

    source_name: str = ""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = (
            "SeedingQDArchive/1.0 (academic research data pipeline; "
            "github.com/your-org/Seeding-QDArchive)"
        )

    # ── Public interface ───────────────────────────────────────────────────────

    def fetch_all(self) -> list[dict]:
        """
        Search all configured QDA terms and return deduplicated metadata dicts.
        Only records with open licenses are returned.
        """
        records = []
        for term in config.QDA_SEARCH_TERMS:
            logger.info("[%s] Searching: '%s'", self.source_name, term)
            try:
                results = self._search(term)
                for r in results:
                    r.setdefault("query_string", term)
                records.extend(results)
                logger.info(
                    "[%s] '%s' -> %d records with open licenses",
                    self.source_name, term, len(results),
                )
            except Exception as exc:
                logger.warning(
                    "[%s] Error on term '%s': %s", self.source_name, term, exc
                )
            time.sleep(config.REQUEST_DELAY)

        # Deduplicate by download_url
        seen, unique = set(), []
        for r in records:
            key = r.get("download_url", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(r)

        logger.info("[%s] Total unique records: %d", self.source_name, len(unique))
        return unique

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get(self, url: str, **kwargs) -> requests.Response:
        """GET with automatic retry on 429 (respects Retry-After if present)."""
        for attempt in range(4):
            resp = self.session.get(url, timeout=config.REQUEST_TIMEOUT, **kwargs)
            if resp.status_code != 429:
                resp.raise_for_status()
                return resp
            wait = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
            logger.warning(
                "[%s] 429 rate-limited — waiting %ds (attempt %d/4): %s",
                self.source_name, wait, attempt + 1, url,
            )
            time.sleep(wait)
        resp.raise_for_status()   # raise after 4 failed attempts
        return resp

    def _check_license(self, license_text: str, title: str = "") -> tuple[bool, str]:
        """
        Returns (is_open: bool, clean_label: str).
        Use this in every scraper instead of rolling your own check.
        """
        if not is_open(license_text, record_title=title):
            return False, ""
        return True, classify(license_text)

    def _scope(self, file_ext: str) -> str:
        ext = file_ext.lower() if file_ext.startswith(".") else f".{file_ext.lower()}"
        if ext in config.QDA_EXTENSIONS:
            return "QDA"
        if ext in config.MEDIA_EXTENSIONS:
            return "Media"
        if ext in config.TEXT_EXTENSIONS or ext in config.STRUCTURED_EXTENSIONS:
            return "Qualitative"
        return "Other"

    # ── Abstract ───────────────────────────────────────────────────────────────

    @abstractmethod
    def _search(self, term: str) -> list[dict]:
        """Search for `term` and return a list of open-licensed metadata dicts."""
        ...
