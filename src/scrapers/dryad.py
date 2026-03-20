"""
Dryad scraper — uses the public Dryad API v2.
Docs: https://datadryad.org/api/v2/docs/

All Dryad datasets are published under CC0 (Creative Commons Zero) by policy.
No per-record license check is needed, but we confirm it from the API anyway.
"""

import logging
import time

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)

DRYAD_API = "https://datadryad.org/api/v2"


class DryadScraper(BaseScraper):
    source_name = "Dryad"

    def _search(self, term: str) -> list[dict]:
        records = []
        page    = 1

        while (page - 1) * config.PAGE_SIZE < config.MAX_RECORDS:
            params = {
                "q":        term,
                "per_page": config.PAGE_SIZE,
                "page":     page,
            }
            try:
                data = self._get(f"{DRYAD_API}/datasets", params=params).json()
            except Exception as exc:
                logger.warning("[Dryad] Search error page %d: %s", page, exc)
                break

            datasets = data.get("_embedded", {}).get("stash:datasets", [])
            if not datasets:
                break

            for ds in datasets:
                ds_id    = ds.get("identifier", "")
                ds_url   = ds.get("_links", {}).get("stash:landing-page", {}).get("href", "")
                title    = ds.get("title", "")
                abstract = ds.get("abstract", "")
                authors  = " | ".join(
                    f"{a.get('firstName', '')} {a.get('lastName', '')}".strip()
                    for a in ds.get("authors", [])
                )
                date_pub = (ds.get("publicationDate") or ds.get("lastModificationDate") or "")[:10]
                keywords = " | ".join(ds.get("keywords", []))

                # Dryad is CC0 by policy — confirm from API if present
                raw_license = ds.get("license", "https://creativecommons.org/publicdomain/zero/1.0/")
                ok, clean_license = self._check_license(
                    raw_license if raw_license else "CC0", title=title
                )
                if not ok:
                    continue  # shouldn't happen, but be strict

                # Fetch files for this dataset
                files = self._fetch_files(ds_id)
                for f in files:
                    fname = f.get("path", "")
                    ext   = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
                    if ext not in config.ALL_WANTED_EXTENSIONS:
                        continue

                    dl_url = f.get("_links", {}).get("stash:file-download", {}).get("href", "")
                    if not dl_url:
                        continue
                    # Dryad download links are relative — make absolute
                    if dl_url.startswith("/"):
                        dl_url = f"https://datadryad.org{dl_url}"

                    records.append({
                        "source":         self.source_name,
                        "source_link":    ds_url or f"https://datadryad.org/dataset/{ds_id}",
                        "download_url":   dl_url,
                        "title":          title,
                        "description":    abstract,
                        "authors":        authors,
                        "date_published": date_pub,
                        "license":        clean_license,
                        "license_url":    "https://creativecommons.org/publicdomain/zero/1.0/",
                        "file_type":      ext.lstrip("."),
                        "file_name":      fname,
                        "file_size":      f.get("size", 0),
                        "project_scope":  self._scope(ext),
                        "keywords":       keywords,
                        "language":       "",
                    })

            page += 1
            time.sleep(config.REQUEST_DELAY)

        return records

    def _fetch_files(self, dataset_id: str) -> list[dict]:
        try:
            # dataset_id is a DOI like "doi:10.5061/dryad.xxxxx"
            encoded = dataset_id.replace("/", "%2F")
            url     = f"{DRYAD_API}/datasets/{encoded}/files"
            data    = self._get(url).json()
            return data.get("_embedded", {}).get("stash:files", [])
        except Exception as exc:
            logger.warning("[Dryad] File list error for %s: %s", dataset_id, exc)
            return []
