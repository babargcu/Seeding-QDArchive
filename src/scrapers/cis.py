"""
CIS (Centro de Investigaciones Sociológicas) scraper.
https://www.cis.es/

Spain's national sociological research centre. Hosts quantitative barometers
AND qualitative interview/focus-group studies.

The CIS catalogue is a Liferay portal that loads results dynamically via
JavaScript, so static HTML scraping of the listing page returns nothing useful.

Strategy
--------
1. Fetch the catalogue page; parse any study IDs that may be embedded in HTML.
2. Probe a configured range of study numbers with HEAD requests to discover
   which documents actually exist (polite — 1 s delay).
3. For each live study, try to fetch the study detail page and collect metadata.
   Fall back to derived metadata (study number + document URL) if unavailable.

Known document URL patterns
---------------------------
Marginales (field results):
    https://www.cis.es/documents/d/cis/es{N}mar-pdf
    https://www.cis.es/documents/d/guest/es{N}mar-pdf
Questionnaire:
    https://www.cis.es/documents/d/cis/cues{N}-pdf
Technical report (ficha técnica):
    https://www.cis.es/documents/d/cis/ft{N}-pdf

All records collected regardless of license — license is recorded, not filtered.
"""

import logging
import re
import time

from bs4 import BeautifulSoup

import config
from src.license_checker import classify
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL    = "https://www.cis.es"
CATALOG_URL = f"{BASE_URL}/en/studies/catalogue"

# Document URL templates: (label, url_template)
# {N} = zero-padded study number (4 digits for recent studies)
_DOC_TEMPLATES = [
    ("marginales",   f"{BASE_URL}/documents/d/cis/es{{N}}mar-pdf"),
    ("marginales",   f"{BASE_URL}/documents/d/guest/es{{N}}mar-pdf"),
    ("cuestionario", f"{BASE_URL}/documents/d/cis/cues{{N}}-pdf"),
    ("ficha",        f"{BASE_URL}/documents/d/cis/ft{{N}}-pdf"),
]

# CIS studies older than 2000 sometimes have CSV/SPSS data files
_DATA_TEMPLATES = [
    ("datos",        f"{BASE_URL}/documents/d/cis/es{{N}}bd"),
    ("datos_csv",    f"{BASE_URL}/documents/d/cis/es{{N}}csv"),
]

# CIS data-reuse conditions page (standard for all studies)
_CIS_LICENSE_URL = "https://www.cis.es/en/studies/general-information"
_CIS_LICENSE     = "CIS Reuse Conditions"

# Skip IDs that are placeholders or navigation
_SKIP_IDS = {
    "catalogue", "catalog", "studies", "estudios", "fid",
    "peticiones-especificas", "general-information",
}


class CISScraper(BaseScraper):
    source_name = "CIS"

    # ── Public interface ───────────────────────────────────────────────────────

    def fetch_all(self) -> list[dict]:
        """
        Collect study IDs from:
          a) the catalogue HTML (if any IDs are embedded)
          b) probing the configured study-number range
        Then scrape each study.
        """
        study_numbers: set[int] = set()

        # (a) Try to extract study numbers from the catalogue page HTML
        catalogue_numbers = self._scrape_catalogue_for_ids()
        study_numbers.update(catalogue_numbers)
        logger.info(
            "[CIS] Found %d study numbers from catalogue HTML",
            len(catalogue_numbers),
        )

        # (b) Probe the configured range
        probed = self._probe_study_range(
            config.CIS_STUDY_START,
            config.CIS_STUDY_END,
            exclude=study_numbers,
        )
        study_numbers.update(probed)
        logger.info(
            "[CIS] Probe found %d additional studies (total: %d)",
            len(probed), len(study_numbers),
        )

        records: list[dict] = []
        for n in sorted(study_numbers, reverse=True):
            recs = self._scrape_study(n)
            records.extend(recs)
            time.sleep(config.REQUEST_DELAY)

        # Deduplicate by download_url
        seen, unique = set(), []
        for r in records:
            key = r.get("download_url") or r.get("source_link", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(r)

        logger.info("[CIS] Total unique records: %d", len(unique))
        return unique

    # ── Catalogue HTML parsing ─────────────────────────────────────────────────

    def _scrape_catalogue_for_ids(self) -> list[int]:
        """
        Try to find study numbers embedded in the catalogue page static HTML.
        The Liferay page is mostly dynamic, so this may return very little,
        but we try several known URL formats.
        """
        numbers: list[int] = []
        urls_to_try = [
            f"{CATALOG_URL}?catalogo=estudio&sort=publishDate-&t=0",
            f"{BASE_URL}/estudios/catalogo?catalogo=estudio&sort=createDateBDE-&t=0",
        ]
        for url in urls_to_try:
            try:
                resp = self._get(url)
                numbers.extend(self._find_study_numbers(resp.text))
                time.sleep(config.REQUEST_DELAY)
            except Exception as exc:
                logger.debug("[CIS] Catalogue URL %s failed: %s", url, exc)
        return list(set(numbers))

    def _find_study_numbers(self, html: str) -> list[int]:
        """Extract CIS study numbers (3-4 digit integers) from arbitrary HTML."""
        numbers: list[int] = []
        # Look for patterns like /estudio-3478, estudio=3478, /3478, es3478
        for m in re.finditer(
            r"(?:estudio[=-/]|/es)(\d{3,5})(?:\b|mar|bd|csv)", html, re.I
        ):
            n = int(m.group(1))
            if config.CIS_STUDY_START <= n <= config.CIS_STUDY_END:
                numbers.append(n)
        return numbers

    # ── Study-number probing ───────────────────────────────────────────────────

    def _probe_study_range(
        self, start: int, end: int, exclude: set[int]
    ) -> list[int]:
        """
        HEAD-request the marginals PDF for each study number in [start, end].
        Returns numbers where at least one document URL returns HTTP 200.
        Rate-limited to config.REQUEST_DELAY between requests.
        """
        found: list[int] = []
        # Only probe study numbers NOT already collected from catalogue
        to_probe = [n for n in range(end, start - 1, -1) if n not in exclude]
        logger.info("[CIS] Probing %d study numbers (%d–%d)…", len(to_probe), start, end)

        for n in to_probe:
            if self._study_exists(n):
                found.append(n)
            time.sleep(config.REQUEST_DELAY)

        return found

    # Short timeout used only for existence probing — avoids 30s waits on dead URLs
    _PROBE_TIMEOUT = 5

    def _study_exists(self, n: int) -> bool:
        """Return True if at least one known document URL for study N is live."""
        for _label, tmpl in _DOC_TEMPLATES[:2]:  # check marginals only for probe
            url = tmpl.format(N=n)
            try:
                resp = self.session.head(
                    url, timeout=self._PROBE_TIMEOUT, allow_redirects=True
                )
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
        return False

    # ── Study detail scraping ──────────────────────────────────────────────────

    def _scrape_study(self, n: int) -> list[dict]:
        """
        Build records for a single CIS study number.
        Tries to fetch the study detail page for metadata; falls back to
        document-URL-only records if detail page is unavailable.
        """
        detail_url = self._find_detail_url(n)
        title, desc, authors, date_pub, keywords = self._scrape_detail(detail_url, n)

        # local_dir = the per-study download subdirectory (e.g. "estudio-3478")
        local_dir = f"estudio-{n}"

        records: list[dict] = []

        for label, tmpl in (_DOC_TEMPLATES + _DATA_TEMPLATES):
            doc_url = tmpl.format(N=n)
            try:
                resp = self.session.head(
                    doc_url, timeout=config.REQUEST_TIMEOUT, allow_redirects=True
                )
            except Exception:
                continue

            if resp.status_code != 200:
                continue

            fsize        = int(resp.headers.get("Content-Length", 0))
            content_type = resp.headers.get("Content-Type", "")
            ext          = self._ext_from_url_or_ct(doc_url, content_type)
            fname        = f"es{n}_{label}{ext}"

            records.append(self._record(
                title=title, desc=desc, authors=authors, date=date_pub,
                keywords=keywords,
                source_link=detail_url or doc_url,
                dl_url=doc_url,
                fname=fname, fsize=fsize, ext=ext,
                local_dir=local_dir,
            ))
            time.sleep(config.REQUEST_DELAY)

        if not records:
            records.append(self._record(
                title=title, desc=desc, authors=authors, date=date_pub,
                keywords=keywords,
                source_link=detail_url or f"{BASE_URL}/estudios/{n}",
                dl_url="", fname="", fsize=0, ext="",
                local_dir=local_dir,
            ))

        return records

    def _find_detail_url(self, n: int) -> str:
        """Return best-guess detail URL for study N."""
        candidates = [
            f"{BASE_URL}/-/estudio-{n}",
            f"{BASE_URL}/en/studies/catalogue/-/estudio-{n}",
        ]
        for url in candidates:
            try:
                r = self.session.head(
                    url, timeout=self._PROBE_TIMEOUT, allow_redirects=True
                )
                if r.status_code == 200:
                    return url
            except Exception:
                pass
        return ""

    def _scrape_detail(
        self, url: str, n: int
    ) -> tuple[str, str, str, str, str]:
        """
        Try to fetch a study detail page and parse metadata.
        Returns (title, description, authors, date_published, keywords).
        Falls back to sensible defaults if unavailable.
        """
        default_title = f"CIS Study {n}"
        if not url:
            return default_title, "", "", "", ""
        try:
            resp = self._get(url)
        except Exception:
            return default_title, "", "", "", ""

        soup = BeautifulSoup(resp.text, "lxml")

        title = (
            self._text(soup, ["h1.title", "h1", ".study-title", ".article-title"])
            or default_title
        )
        desc = self._text(soup, [
            ".abstract", ".description", ".study-abstract",
            ".portlet-body p", "article p",
        ])
        authors  = self._text(soup, [".author", ".authors", ".researchers"])
        date_pub = self._text(soup, [".date", ".publication-date", "time"])
        keywords = self._text(soup, [".keywords", ".tags", ".subjects"])

        # Clean up date — keep only YYYY or YYYY-MM-DD
        m = re.search(r"\d{4}(?:-\d{2}-\d{2})?", date_pub)
        date_pub = m.group() if m else ""

        return title, desc[:2000], authors, date_pub, keywords

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _ext_from_url_or_ct(self, url: str, content_type: str) -> str:
        """Derive a file extension from URL path or Content-Type header."""
        url_lower = url.lower()
        for ext in sorted(config.ALL_WANTED_EXTENSIONS, key=len, reverse=True):
            if url_lower.endswith(ext) or url_lower.endswith(ext.lstrip(".")):
                return ext
        ct = content_type.split(";")[0].strip().lower()
        ct_map = {
            "application/pdf":    ".pdf",
            "application/zip":    ".zip",
            "text/csv":           ".csv",
            "application/json":   ".json",
            "application/xml":    ".xml",
            "text/html":          ".html",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/vnd.ms-excel": ".xls",
            "application/octet-stream": "",
        }
        return ct_map.get(ct, ".pdf")  # default .pdf for CIS documents

    def _text(self, soup: BeautifulSoup, selectors: list[str]) -> str:
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                return el.get_text(separator=" ", strip=True)
        return ""

    def _record(self, *, title, desc, authors, date, keywords,
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
            "uploader_name":   "CIS",
            "uploader_email":  "",
            "date_published":  date,
            "license":         _CIS_LICENSE,
            "license_url":     _CIS_LICENSE_URL,
            "file_type":       ext.lstrip("."),
            "file_size":       int(fsize) if fsize else 0,
            "project_scope":   self._scope(ext) if ext else "Other",
            "keywords":        keywords,
            "language":        "es",
        }

    def _search(self, term: str) -> list[dict]:
        # fetch_all() is overridden — this is never called
        return []
