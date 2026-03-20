"""
OSF (Open Science Framework) scraper — uses the OSF API v2.
Docs: https://developer.osf.io/

License note: Many OSF projects do not set an explicit license.
Per project rules: no license = skip. We only include projects
where a license is clearly stated and recognized as open.
"""

import logging
import time

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)

OSF_NODES = "https://api.osf.io/v2/nodes/"


class OSFScraper(BaseScraper):
    source_name = "OSF"

    def __init__(self):
        super().__init__()
        if config.OSF_TOKEN:
            self.session.headers["Authorization"] = f"Bearer {config.OSF_TOKEN}"

    def _search(self, term: str) -> list[dict]:
        records = []
        url     = OSF_NODES
        params  = {
            "filter[search]": term,
            "filter[public]": "true",
            "page[size]":     config.PAGE_SIZE,
        }
        fetched = 0

        while url and fetched < config.MAX_RECORDS:
            try:
                resp = self._get(url, params=params).json()
            except Exception as exc:
                logger.warning("[OSF] API error: %s", exc)
                break

            for node in resp.get("data", []):
                attrs    = node.get("attributes", {})
                node_id  = node.get("id", "")
                node_url = f"https://osf.io/{node_id}/"
                title    = attrs.get("title", "")

                # Fetch the node's license explicitly — OSF often omits it
                raw_license = (attrs.get("node_license") or {}).get("name", "")
                if not raw_license:
                    raw_license = self._fetch_node_license(node_id)

                ok, clean = self._check_license(raw_license, title=title)
                if not ok:
                    continue   # no license or unrecognised = skip

                authors  = ""   # contributor fetch would add extra API calls; skip for speed
                tags     = " | ".join(attrs.get("tags", []))
                date_pub = (attrs.get("date_created") or "")[:10]

                file_records = self._fetch_files(
                    node_id, node_url, title,
                    attrs.get("description", ""),
                    authors, date_pub, clean, tags,
                )
                records.extend(file_records)
                fetched += 1
                time.sleep(config.REQUEST_DELAY)

            url    = resp.get("links", {}).get("next")
            params = {}

        return records

    def _fetch_node_license(self, node_id: str) -> str:
        try:
            data = self._get(f"https://api.osf.io/v2/nodes/{node_id}/").json()
            return (
                data.get("data", {})
                    .get("attributes", {})
                    .get("node_license", {}) or {}
            ).get("name", "")
        except Exception:
            return ""

    def _fetch_files(
        self, node_id, node_url, title, description,
        authors, date_pub, license_name, tags,
    ) -> list[dict]:
        records = []
        url = f"https://api.osf.io/v2/nodes/{node_id}/files/osfstorage/"
        while url:
            try:
                resp = self._get(url).json()
            except Exception as exc:
                logger.warning("[OSF] File error for node %s: %s", node_id, exc)
                break

            for f in resp.get("data", []):
                attrs  = f.get("attributes", {})
                fname  = attrs.get("name", "")
                ext    = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
                if ext not in config.ALL_WANTED_EXTENSIONS:
                    continue

                dl_url = (f.get("links") or {}).get("download", "")
                if not dl_url:
                    continue

                records.append({
                    "source":         self.source_name,
                    "source_link":    node_url,
                    "download_url":   dl_url,
                    "title":          title,
                    "description":    description,
                    "authors":        authors,
                    "date_published": date_pub,
                    "license":        license_name,
                    "license_url":    "",
                    "file_type":      ext.lstrip("."),
                    "file_name":      fname,
                    "file_size":      attrs.get("size", 0),
                    "project_scope":  self._scope(ext),
                    "keywords":       tags,
                    "language":       "",
                })

            url = resp.get("links", {}).get("next")

        return records
