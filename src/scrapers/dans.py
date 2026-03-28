"""
DANS (Data Archiving and Networked Services) scraper.
Uses the OAI-PMH standard metadata harvesting protocol.

Endpoint: https://ssh.datastations.nl/oai  (DANS SSH Data Station)
Protocol: OAI-PMH 2.0 with Dublin Core (oai_dc) metadata format
Docs: https://dans.knaw.nl/en/data-services-and-infrastructure/

Note: The original DANS EASY endpoint (easy.dans.knaw.nl) was migrated to
the DANS Data Stations in 2023. SSH (Social Sciences & Humanities) data
is now at ssh.datastations.nl.

OAI-PMH provides metadata and record-page URLs only.
download_url points to the landing page.

DANS licenses vary — we skip records without a recognized open license.
"""

import logging
import time
import xml.etree.ElementTree as ET

import config
from .base import BaseScraper

logger = logging.getLogger(__name__)

DANS_OAI = "https://ssh.datastations.nl/oai"

# Dublin Core namespace
DC  = "http://purl.org/dc/elements/1.1/"
OAI = "http://www.openarchives.org/OAI/2.0/"


class DANSScraper(BaseScraper):
    source_name = "DANS SSH"

    def fetch_all(self) -> list[dict]:
        """
        Override: DANS OAI-PMH uses resumption tokens rather than search terms.
        We harvest all records and filter locally by keyword relevance.
        """
        logger.info("[DANS] Starting OAI-PMH harvest (this may take a while)…")
        records        = []
        resumption     = None
        harvested      = 0
        max_harvest    = config.MAX_RECORDS * len(config.QDA_SEARCH_TERMS)
        keywords_lower = [t.lower() for t in config.QDA_SEARCH_TERMS]

        while harvested < max_harvest:
            params: dict = {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
            if resumption:
                params = {"verb": "ListRecords", "resumptionToken": resumption}

            try:
                resp = self._get(DANS_OAI, params=params)
                root = ET.fromstring(resp.content)
            except Exception as exc:
                logger.warning("[DANS] OAI-PMH error: %s", exc)
                break

            for record in root.iter(f"{{{OAI}}}record"):
                meta = record.find(f".//{{{OAI}}}metadata")
                if meta is None:
                    continue
                rec = self._parse_dc(meta)
                if not rec:
                    continue

                # Filter by keyword relevance
                combined = (
                    rec.get("title", "") + " " +
                    rec.get("description", "") + " " +
                    rec.get("keywords", "")
                ).lower()
                if not any(kw in combined for kw in keywords_lower):
                    continue

                # License check (strict)
                ok, clean = self._check_license(rec.get("license", ""), title=rec.get("title", ""))
                if not ok:
                    continue

                rec["license"] = clean
                records.append(rec)
                harvested += 1

            # Resumption token for next page
            token_el = root.find(f".//{{{OAI}}}resumptionToken")
            if token_el is not None and token_el.text:
                resumption = token_el.text.strip()
            else:
                break

            time.sleep(config.REQUEST_DELAY)

        logger.info("[DANS] Harvested %d matching records", len(records))
        return records

    def _search(self, term: str) -> list[dict]:
        # Not used — DANS uses fetch_all() override above
        return []

    def _parse_dc(self, meta_element) -> dict | None:
        """Parse a Dublin Core metadata block into our record format."""
        def _get(tag):
            el = meta_element.find(f".//{{{DC}}}{tag}")
            return el.text.strip() if el is not None and el.text else ""

        def _get_all(tag):
            return " | ".join(
                el.text.strip()
                for el in meta_element.findall(f".//{{{DC}}}{tag}")
                if el.text
            )

        identifier = _get("identifier")
        if not identifier:
            return None

        # identifier is usually a URL to the landing page
        source_link = identifier if identifier.startswith("http") else ""

        # dc:format may hint at file types
        formats  = _get_all("format")
        # dc:rights holds the license
        rights   = _get("rights")
        # dc:type
        dc_type  = _get_all("type")

        # Guess file type from format field or type
        ext = self._guess_ext(formats + " " + dc_type)

        return {
            "source":         self.source_name,
            "source_link":    source_link,
            "download_url":   source_link,   # landing page only; no direct file URL from OAI-PMH
            "title":          _get("title"),
            "description":    _get("description"),
            "authors":        _get_all("creator"),
            "date_published": _get("date")[:10] if _get("date") else "",
            "license":        rights,
            "license_url":    "",
            "file_type":      ext,
            "file_name":      "",
            "file_size":      0,
            "project_scope":  "Qualitative",
            "keywords":       _get_all("subject"),
            "language":       _get("language"),
        }

    def _guess_ext(self, format_text: str) -> str:
        """Guess file extension from dc:format / dc:type text."""
        t = format_text.lower()
        if "pdf" in t:          return "pdf"
        if "word" in t:         return "docx"
        if "excel" in t:        return "xlsx"
        if "audio" in t:        return "mp3"
        if "video" in t:        return "mp4"
        if "text" in t:         return "txt"
        if "nvivo" in t:        return "nvp"
        if "atlas" in t:        return "atlproj"
        if "maxqda" in t:       return "mxd"
        if "qdpx" in t:         return "qdpx"
        return ""
