"""
Figshare scraper — uses the public Figshare API v2.
Docs: https://docs.figshare.com/

Figshare assigns CC BY by default, but individual items can have other licenses.
We check every record's license individually via the article detail endpoint.
"""

import logging
import time

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)

FIGSHARE_SEARCH  = "https://api.figshare.com/v2/articles/search"
FIGSHARE_ARTICLE = "https://api.figshare.com/v2/articles/{article_id}"


class FigshareScraper(BaseScraper):
    source_name = "Figshare"

    def __init__(self):
        super().__init__()
        if config.FIGSHARE_TOKEN:
            self.session.headers["Authorization"] = f"token {config.FIGSHARE_TOKEN}"

    def _search(self, term: str) -> list[dict]:
        records = []
        page    = 1

        while (page - 1) * config.PAGE_SIZE < config.MAX_RECORDS:
            params = {
                "search_for": term,
                "item_type":  3,          # 3 = dataset
                "page":       page,
                "page_size":  config.PAGE_SIZE,
            }
            try:
                resp = self.session.post(
                    FIGSHARE_SEARCH,
                    json={"search_for": term, "item_type": 3,
                          "page": page, "page_size": config.PAGE_SIZE},
                    timeout=config.REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                articles = resp.json()
            except Exception as exc:
                logger.warning("[Figshare] Search error page %d: %s", page, exc)
                break

            if not articles:
                break

            for article in articles:
                article_id  = article.get("id")
                article_url = article.get("url_public_html", "")

                try:
                    detail = self._get(
                        FIGSHARE_ARTICLE.format(article_id=article_id)
                    ).json()
                    time.sleep(config.REQUEST_DELAY)
                except Exception as exc:
                    logger.warning("[Figshare] Detail error for %s: %s", article_id, exc)
                    continue

                license_info = detail.get("license") or {}
                raw_license  = license_info.get("name", "")
                title        = detail.get("title", "")

                ok, clean = self._check_license(raw_license, title=title)
                if not ok:
                    continue

                authors  = " | ".join(
                    a.get("full_name", "") for a in detail.get("authors", [])
                )
                keywords = " | ".join(detail.get("tags", []))
                date_pub = (detail.get("published_date") or "")[:10]

                for file_info in detail.get("files", []):
                    fname = file_info.get("name", "")
                    ext   = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
                    if ext not in config.ALL_WANTED_EXTENSIONS:
                        continue

                    dl_url = file_info.get("download_url", "")
                    if not dl_url:
                        continue

                    records.append({
                        "source":         self.source_name,
                        "source_link":    article_url,
                        "download_url":   dl_url,
                        "title":          title,
                        "description":    detail.get("description", ""),
                        "authors":        authors,
                        "date_published": date_pub,
                        "license":        clean,
                        "license_url":    license_info.get("url", ""),
                        "file_type":      ext.lstrip("."),
                        "file_name":      fname,
                        "file_size":      file_info.get("size", 0),
                        "project_scope":  self._scope(ext),
                        "keywords":       keywords,
                        "language":       "",
                    })

            page += 1
            time.sleep(config.REQUEST_DELAY)

        return records
