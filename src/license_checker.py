"""
License checker for the QDArchive seeding pipeline.

Rules (from project requirements):
    - Any Creative Commons license  → ACCEPT
    - Other recognized open licenses → ACCEPT
    - No license / empty             → REJECT  (treat as proprietary)
    - Unknown / proprietary text     → REJECT

This module is the single source of truth for license decisions.
"""

import re
import logging

logger = logging.getLogger(__name__)

# ── Creative Commons patterns ──────────────────────────────────────────────────
# Matches: CC0, CC BY, CC BY-SA, CC BY-NC, CC BY-ND, CC BY-NC-SA, CC BY-NC-ND
# and variations with spaces, dashes, version numbers, SPDX ids, etc.
_CC_REGEX = re.compile(
    r'\b(cc[\s\-]?0|cc[\s\-]?zero|creative[\s\-]commons[\s\-]zero'
    r'|cc[\s\-]by[\s\-]?(sa|nc|nd|nc[\s\-]?sa|nc[\s\-]?nd)?'
    r'|creative[\s\-]commons[\s\-]attribution)',
    re.IGNORECASE,
)

# ── Other recognized open licenses ────────────────────────────────────────────
_OTHER_OPEN = [
    "public domain",
    "open data commons",
    "odc-by",
    "odbl",
    "open database license",
    "pddl",
    "public domain dedication",
    "open government licence",
    "open government license",
    "data licence germany",          # DANS / German archives
    "dl-de",
    "dans licence",                  # DANS Data Station open reuse licence
    "dans license",
    "community data license",
    "cdla",
    "mit license",
    "apache license",
    "gnu general public",
    "gnu lesser",
]

# ── Keywords that strongly indicate a closed/proprietary license ───────────────
# If any of these appear, reject immediately even if "open" is also mentioned.
_CLOSED_INDICATORS = [
    "all rights reserved",
    "proprietary",
    "not for redistribution",
    "commercial use prohibited",     # some NC-only variants we still accept above
    "no derivatives",                # CC BY-ND is still CC so accepted via regex
    "restricted access",
    "confidential",
]


def is_open(license_text: str, record_title: str = "") -> bool:
    """
    Return True only if the license is a known open license.

    Args:
        license_text:  The license string from the data source API.
        record_title:  Optional — used only for logging context.

    Returns:
        True  → open license, safe to include.
        False → no license or unrecognised license, skip this record.
    """
    if not license_text or not license_text.strip():
        logger.debug("SKIP (no license): %s", record_title or "unknown")
        return False

    text = license_text.strip().lower()

    # Reject if closed indicators are present
    for indicator in _CLOSED_INDICATORS:
        if indicator in text:
            logger.debug("SKIP (closed indicator '%s'): %s", indicator, record_title or license_text)
            return False

    # Accept Creative Commons
    if _CC_REGEX.search(text):
        return True

    # Accept other open licenses
    for kw in _OTHER_OPEN:
        if kw in text:
            return True

    logger.debug("SKIP (unrecognised license '%s'): %s", license_text, record_title or "unknown")
    return False


def classify(license_text: str) -> str:
    """
    Return a short human-readable license category string.
    Used for the 'license' column in the metadata DB.
    """
    if not license_text:
        return ""
    text = license_text.strip()
    t = text.lower()

    if "cc0" in t or "cc-0" in t or "zero" in t:
        return "CC0"
    if _CC_REGEX.search(t):
        # Try to extract the variant cleanly
        match = re.search(
            r'cc[\s\-]?(by[\s\-]?(?:sa|nc|nd|nc[\s\-]?sa|nc[\s\-]?nd)?)',
            t, re.IGNORECASE,
        )
        if match:
            variant = re.sub(r'\s+', '-', match.group().upper().strip())
            # Try to find version number e.g. 4.0
            ver = re.search(r'\d+\.\d+', text)
            return f"{variant} {ver.group()}" if ver else variant
        return "Creative Commons"
    if "public domain" in t:
        return "Public Domain"
    if "odbl" in t or "open database" in t:
        return "ODbL"
    if "odc-by" in t:
        return "ODC-BY"
    if "open government" in t:
        return "Open Government Licence"
    if "dl-de" in t or "data licence germany" in t:
        return "Data Licence Germany"
    if "dans licence" in t or "dans license" in t:
        return "DANS Licence"

    return text[:80]   # fallback: truncated original
