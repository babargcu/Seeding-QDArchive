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

OSF_SEARCH = "https://api.osf.io/v2/search/projects/"


class OSFScraper(BaseScraper):
    source_name = "OSF"

    def __init__(self):
        super().__init__()
        if config.OSF_TOKEN:
            self.session.headers["Authorization"] = f"Bearer {config.OSF_TOKEN}"

    # Hard cap: inspect at most this many nodes per search term regardless of
    # how many are licensed. Prevents hours-long loops on broad terms like
    # 'interview transcript' where 99% of results have no license.
    _MAX_NODES_PER_TERM = 500

    def _search(self, term: str) -> list[dict]:
        records       = []
        url           = OSF_SEARCH
        params        = {
            "q":          term,
            "page[size]": config.PAGE_SIZE,
        }
        fetched       = 0   # licensed nodes that produced file records
        total_checked = 0   # total nodes inspected (hard cap)

        while url and fetched < config.MAX_RECORDS and total_checked < self._MAX_NODES_PER_TERM:
            try:
                resp = self._get(url, params=params).json()
            except Exception as exc:
                logger.warning("[OSF] API error: %s", exc)
                break

            page_nodes = resp.get("data", [])
            if not page_nodes:
                break

            for node in page_nodes:
                if total_checked >= self._MAX_NODES_PER_TERM:
                    break
                total_checked += 1

                attrs    = node.get("attributes", {})
                node_id  = node.get("id", "")
                node_url = f"https://osf.io/{node_id}/"
                title    = attrs.get("title", "")

                # Try inline node_license first, then follow relationship link
                raw_license = (attrs.get("node_license") or {}).get("name", "")
                if not raw_license:
                    raw_license = self._fetch_node_license(node, node_id)

                ok, clean = self._check_license(raw_license, title=title)
                if not ok:
                    continue   # no license or unrecognised = skip

                tags     = " | ".join(attrs.get("tags", []))
                date_pub = (attrs.get("date_created") or "")[:10]

                file_records = self._fetch_files(
                    node_id, node_url, title,
                    attrs.get("description", ""),
                    "", date_pub, clean, tags,
                )
                records.extend(file_records)
                fetched += 1
                time.sleep(config.REQUEST_DELAY)

            url    = resp.get("links", {}).get("next")
            params = {}

        if total_checked >= self._MAX_NODES_PER_TERM:
            logger.info(
                "[OSF] '%s' hit node cap (%d) — %d licensed nodes found",
                term, self._MAX_NODES_PER_TERM, fetched,
            )
        return records

    def _fetch_node_license(self, node: dict, node_id: str) -> str:
        """Follow the relationships.license link for the actual license name."""
        try:
            lic_url = (
                node.get("relationships", {})
                    .get("license", {})
                    .get("links", {})
                    .get("related", {})
                    .get("href", "")
            )
            if lic_url:
                data = self._get(lic_url).json()
                return data.get("data", {}).get("attributes", {}).get("name", "")
        except Exception:
            pass
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
