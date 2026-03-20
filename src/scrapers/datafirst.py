"""
DataFirst scraper — scraping of NADA catalog.
https://www.datafirst.uct.ac.za/dataportal/

DataFirst is a research data service at UCT running NADA (National Data Archive)
software. Hosts African microdata (surveys, censuses, qualitative studies).

All records collected regardless of license — license is recorded, not filtered.
Overrides fetch_all() to paginate all 594+ datasets instead of per-search-term.
"""

import logging
import re
import time

from bs4 import BeautifulSoup

import config
from src.license_checker import classify
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE    = "https://www.datafirst.uct.ac.za/dataportal/index.php"
CATALOG = f"{BASE}/catalog/search"
DETAIL  = f"{BASE}/catalog"

# IDs that appear in catalog URLs but are not actual study IDs
_SKIP_IDS = {
    "search", "central", "history", "index", "get-microdata",
    "export", "variable", "related", "citations", "metadata",
}


class DataFirstScraper(BaseScraper):
    source_name = "DataFirst"

    # ── Public interface ───────────────────────────────────────────────────────

    def fetch_all(self) -> list[dict]:
        """Paginate through the full NADA catalog; return all file records."""
        study_ids = self._collect_all_ids()
        logger.info("[DataFirst] Collected %d unique study IDs", len(study_ids))

        records = []
        for idno in study_ids:
            recs = self._scrape_study(idno)
            records.extend(recs)
            time.sleep(config.REQUEST_DELAY)

        # Deduplicate by download_url (or source_link for metadata-only entries)
        seen, unique = set(), []
        for r in records:
            key = r.get("download_url") or r.get("source_link", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(r)

        logger.info("[DataFirst] Total unique records: %d", len(unique))
        return unique

    # ── Catalog pagination ─────────────────────────────────────────────────────

    def _collect_all_ids(self) -> list[str]:
        """Paginate catalog search HTML and return all unique study IDs."""
        seen: set[str] = set()
        ids: list[str] = []
        page = 1

        while True:
            try:
                resp = self._get(CATALOG, params={
                    "ps":         100,
                    "page":       page,
                    "sort_by":    "year",
                    "sort_order": "desc",
                })
            except Exception as exc:
                logger.warning("[DataFirst] Catalog page %d error: %s", page, exc)
                break

            soup = BeautifulSoup(resp.text, "lxml")
            new_ids: list[str] = []

            for a in soup.find_all("a", href=True):
                m = re.search(r"/catalog/([^/?#\s]+)(?:[/?#]|$)", a["href"])
                if not m:
                    continue
                idno = m.group(1)
                if idno in _SKIP_IDS or idno in seen:
                    continue
                # Must look like a real study ID (letters/digits/hyphens/dots)
                if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]+$", idno):
                    continue
                seen.add(idno)
                new_ids.append(idno)
                ids.append(idno)

            logger.info(
                "[DataFirst] Page %d → %d new IDs (total: %d)",
                page, len(new_ids), len(ids),
            )

            if not new_ids:
                logger.info("[DataFirst] No new IDs on page %d — stopping", page)
                break

            # Safety cap
            if len(ids) >= 2000:
                logger.info("[DataFirst] Reached 2000 IDs — stopping pagination")
                break

            page += 1
            time.sleep(config.REQUEST_DELAY)

        return ids

    # ── Study detail scraping ──────────────────────────────────────────────────

    def _scrape_study(self, idno: str) -> list[dict]:
        """Fetch one study detail page and return one record per file found."""
        url = f"{DETAIL}/{idno}"
        try:
            resp = self._get(url)
        except Exception as exc:
            logger.debug("[DataFirst] Study %s error: %s", idno, exc)
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # ── Metadata ──────────────────────────────────────────────────────────
        title = (
            self._text(soup, ["h1.title", "h2.title", ".study-title", "h1", "h2"])
            or idno
        )
        desc = self._text(soup, [
            ".abstract", ".description", "#abstract",
            ".study-abstract", ".notes",
        ])

        meta           = self._extract_kv(soup)
        authors        = meta.get("principal_investigator",
                          meta.get("author",
                          meta.get("producer", "")))
        uploader_name  = meta.get("depositor", meta.get("data_depositor", authors))
        uploader_email = meta.get("depositor_email", meta.get("contact_email", ""))
        date_pub       = meta.get("year", meta.get("date_of_collection",
                          meta.get("date", "")))
        license_raw    = meta.get("license", meta.get("access_conditions",
                          meta.get("access_authority", "")))
        keywords       = meta.get("keywords", meta.get("topics", ""))
        language       = meta.get("language", "")

        license_label = classify(license_raw) if license_raw else ""

        # local_dir = safe version of the study ID (used as the download subdirectory)
        local_dir = _safe_dir(idno)

        # ── Files ─────────────────────────────────────────────────────────────
        file_rows = self._extract_files(soup)

        if not file_rows:
            return [self._record(
                idno=idno, title=title, desc=desc,
                authors=authors, uploader_name=uploader_name, uploader_email=uploader_email,
                date=date_pub, license_label=license_label,
                keywords=keywords, language=language,
                source_link=url, dl_url="", fname="", fsize=0, ext="", local_dir=local_dir,
            )]

        records = []
        for fname, dl_url, fsize in file_rows:
            ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
            records.append(self._record(
                idno=idno, title=title, desc=desc,
                authors=authors, uploader_name=uploader_name, uploader_email=uploader_email,
                date=date_pub, license_label=license_label,
                keywords=keywords, language=language,
                source_link=url, dl_url=dl_url, fname=fname, fsize=fsize, ext=ext,
                local_dir=local_dir,
            ))
        return records

    # ── HTML helpers ──────────────────────────────────────────────────────────

    def _extract_kv(self, soup: BeautifulSoup) -> dict:
        """Extract key-value metadata from NADA dl/dt/dd or table patterns."""
        pairs: dict[str, str] = {}

        # dl / dt / dd
        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                k = re.sub(r"[^a-z0-9]+", "_",
                            dt.get_text(strip=True).lower()).strip("_")
                v = dd.get_text(separator=" ", strip=True)
                if k and v:
                    pairs[k] = v

        # tables with metadata-like class names
        for tbl in soup.find_all("table"):
            cls = " ".join(tbl.get("class", []))
            if not re.search(r"(meta|study|detail|info)", cls, re.I):
                continue
            for row in tbl.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) >= 2:
                    k = re.sub(r"[^a-z0-9]+", "_",
                                cells[0].get_text(strip=True).lower()).strip("_")
                    v = cells[1].get_text(separator=" ", strip=True)
                    if k and v:
                        pairs[k] = v
        return pairs

    def _extract_files(self, soup: BeautifulSoup) -> list[tuple]:
        """Return [(filename, download_url, size_bytes), ...] from page."""
        files: list[tuple] = []
        seen_urls: set[str] = set()

        for a in soup.find_all("a", href=True):
            href: str = a["href"]
            text: str = a.get_text(strip=True)

            # Absolute URL
            if href.startswith("/"):
                href = "https://www.datafirst.uct.ac.za" + href
            elif not href.startswith("http"):
                continue

            if href in seen_urls:
                continue

            # Match by file extension in URL
            lower = href.lower()
            matched_ext = next(
                (e for e in config.ALL_WANTED_EXTENSIONS if lower.endswith(e)),
                None,
            )
            if matched_ext:
                fname = href.split("/")[-1] or (text + matched_ext)
                seen_urls.add(href)
                files.append((fname, href, 0))
                continue

            # NADA download/get-microdata endpoint links
            if "/get-microdata" in href or "/download" in lower:
                fname = text or href.split("/")[-1] or "file"
                seen_urls.add(href)
                files.append((fname, href, 0))

        return files

    def _text(self, soup: BeautifulSoup, selectors: list[str]) -> str:
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                return el.get_text(separator=" ", strip=True)
        return ""

    def _record(self, *, idno, title, desc, authors, uploader_name, uploader_email,
                date, license_label, keywords, language,
                source_link, dl_url, fname, fsize, ext, local_dir) -> dict:
        return {
            "source":          self.source_name,
            "source_link":     source_link,
            "download_url":    dl_url,
            "local_dir":       local_dir,
            "file_name":       fname,
            "title":           title,
            "description":     (desc or "")[:2000],
            "authors":         authors,
            "uploader_name":   uploader_name,
            "uploader_email":  uploader_email,
            "date_published":  date,
            "license":         license_label,
            "license_url":     "",
            "file_type":       ext.lstrip("."),
            "file_size":       int(fsize) if fsize else 0,
            "project_scope":   self._scope(ext) if ext else "Other",
            "keywords":        keywords,
            "language":        language,
        }

    def _search(self, term: str) -> list[dict]:
        # fetch_all() is overridden — this is never called
        return []


def _safe_dir(name: str) -> str:
    """Return a filesystem-safe directory name from a study ID or title."""
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    cleaned = "".join(c if c in keep else "-" for c in name).strip("-")
    return cleaned[:120] or "study"
