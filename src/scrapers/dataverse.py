"""
Generic Dataverse scraper — works with any repository running Dataverse software.

Pre-configured instances (created in pipeline.py):
    - Harvard Dataverse  https://dataverse.harvard.edu
    - DataverseNO        https://dataverse.no
    - QDR Syracuse       https://data.qdr.syr.edu

Dataverse Search API docs:
    https://guides.dataverse.org/en/latest/api/search.html
"""

import logging
import time

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)


class DataverseScraper(BaseScraper):
    """
    Scraper for any Dataverse instance.

    Args:
        base_url:    Root URL of the Dataverse instance.
        source_name: Human-readable name used in the metadata DB.
        api_token:   Optional API token for higher rate limits.
    """

    def __init__(
        self,
        base_url: str = "https://dataverse.harvard.edu",
        source_name: str = "Harvard Dataverse",
        api_token: str = "",
    ):
        super().__init__()
        self.base_url    = base_url.rstrip("/")
        self.source_name = source_name
        if api_token:
            self.session.headers["X-Dataverse-key"] = api_token

    def _search(self, term: str) -> list[dict]:
        records = []
        start   = 0

        while start < config.MAX_RECORDS:
            params = {
                "q":        term,
                "type":     "file",
                "start":    start,
                "per_page": config.PAGE_SIZE,
                "sort":     "date",
                "order":    "desc",
            }
            try:
                data = self._get(
                    f"{self.base_url}/api/search", params=params
                ).json()
            except Exception as exc:
                logger.warning("[%s] Search error at offset %d: %s", self.source_name, start, exc)
                break

            items = data.get("data", {}).get("items", [])
            if not items:
                break

            for item in items:
                fname = item.get("name", "")
                ext   = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
                if ext not in config.ALL_WANTED_EXTENSIONS:
                    continue

                file_id      = item.get("file_id", "")
                download_url = f"{self.base_url}/api/access/datafile/{file_id}" if file_id else ""
                if not download_url:
                    continue

                dataset_pid = item.get("dataset_persistent_id", "")
                dataset_url = item.get("url", f"{self.base_url}/dataset.xhtml?persistentId={dataset_pid}")

                # License — try inline first, then fetch from dataset
                raw_license = (
                    item.get("license_name")
                    or item.get("termsOfUse")
                    or self._fetch_dataset_license(dataset_pid)
                )
                ok, clean_license = self._check_license(raw_license or "", title=fname)
                if not ok:
                    continue

                records.append({
                    "source":         self.source_name,
                    "source_link":    dataset_url,
                    "download_url":   download_url,
                    "title":          item.get("dataset_name", fname),
                    "description":    item.get("dataset_citation", ""),
                    "authors":        " | ".join(item.get("authors", [])),
                    "date_published": (item.get("published_at") or "")[:10],
                    "license":        clean_license,
                    "license_url":    item.get("license_url", ""),
                    "file_type":      ext.lstrip("."),
                    "file_name":      fname,
                    "file_size":      item.get("size_in_bytes", 0),
                    "project_scope":  self._scope(ext),
                    "keywords":       " | ".join(item.get("subjects", [])),
                    "language":       "",
                })

            start += len(items)
            time.sleep(config.REQUEST_DELAY)

        return records

    def _fetch_dataset_license(self, persistent_id: str) -> str:
        if not persistent_id:
            return ""
        try:
            url  = f"{self.base_url}/api/datasets/:persistentId/?persistentId={persistent_id}"
            data = self._get(url).json()
            ver  = data.get("data", {}).get("latestVersion", {})
            lic  = ver.get("license", {})
            return lic.get("name", "") or ver.get("termsOfUse", "")
        except Exception:
            return ""
