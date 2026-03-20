"""
Zenodo scraper — uses the public Zenodo REST API.
Docs: https://developers.zenodo.org/

License: Zenodo stores SPDX identifiers (e.g. "cc-by-4.0", "cc-by-sa-4.0").
We pass the SPDX id to the license checker which handles all CC variants.
"""

import logging
import time

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)

ZENODO_API = "https://zenodo.org/api/records"


class ZenodoScraper(BaseScraper):
    source_name = "Zenodo"

    def __init__(self):
        super().__init__()
        if config.ZENODO_TOKEN:
            self.session.headers["Authorization"] = f"Bearer {config.ZENODO_TOKEN}"

    def _search(self, term: str) -> list[dict]:
        records = []
        page    = 1
        fetched = 0

        while fetched < config.MAX_RECORDS:
            params = {
                "q":      term,
                "type":   "dataset",
                "access_right": "open",
                "size":   config.PAGE_SIZE,
                "page":   page,
                "sort":   "mostrecent",
            }
            try:
                data = self._get(ZENODO_API, params=params).json()
            except Exception as exc:
                logger.warning("[Zenodo] API error page %d: %s", page, exc)
                break

            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                metadata    = hit.get("metadata", {})
                title       = metadata.get("title", "")

                # License — Zenodo uses SPDX ids like "cc-by-4.0"
                license_id  = (metadata.get("license") or {}).get("id", "")
                ok, clean   = self._check_license(license_id, title=title)
                if not ok:
                    continue

                license_url = self._cc_url(license_id)
                record_url  = hit.get("links", {}).get("html", "")
                authors     = " | ".join(
                    c.get("name", "") for c in metadata.get("creators", [])
                )
                keywords    = " | ".join(metadata.get("keywords", []))
                date_pub    = metadata.get("publication_date", "")

                for file_info in hit.get("files", []):
                    fname = file_info.get("key", "")
                    ext   = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
                    if ext not in config.ALL_WANTED_EXTENSIONS:
                        continue

                    dl_url = file_info.get("links", {}).get("self", "")
                    if not dl_url:
                        continue

                    records.append({
                        "source":         self.source_name,
                        "source_link":    record_url,
                        "download_url":   dl_url,
                        "title":          title,
                        "description":    metadata.get("description", ""),
                        "authors":        authors,
                        "date_published": date_pub,
                        "license":        clean,
                        "license_url":    license_url,
                        "file_type":      ext.lstrip("."),
                        "file_name":      fname,
                        "file_size":      file_info.get("size", 0),
                        "project_scope":  self._scope(ext),
                        "keywords":       keywords,
                        "language":       metadata.get("language", ""),
                    })

            fetched += len(hits)
            page    += 1
            time.sleep(config.REQUEST_DELAY)

        return records

    def _cc_url(self, spdx_id: str) -> str:
        """Convert SPDX id to a CC license URL where possible."""
        s = spdx_id.lower()
        if "cc-zero" in s or s == "cc0-1.0":
            return "https://creativecommons.org/publicdomain/zero/1.0/"
        if s.startswith("cc-by"):
            # e.g. cc-by-4.0 → https://creativecommons.org/licenses/by/4.0/
            parts = s.replace("cc-", "").split("-")
            kind  = "/".join(p for p in parts if not p.replace(".", "").isdigit())
            ver   = next((p for p in parts if p.replace(".", "").isdigit()), "4.0")
            return f"https://creativecommons.org/licenses/{kind}/{ver}/"
        return ""
