"""
Central configuration for the Seeding QDArchive pipeline.
Sources: DataFirst (UCT) and CIS (Spain).
Copy .env.example to .env for optional API keys.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data" / "downloads"
DB_PATH    = BASE_DIR / "data" / "metadata.db"
REPORT_DIR = BASE_DIR / "reports"
DOCS_DIR   = BASE_DIR / "docs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Scraper settings ───────────────────────────────────────────────────────────
REQUEST_TIMEOUT  = 30     # seconds per HTTP request
REQUEST_DELAY    = 1.0    # seconds between requests (be polite to servers)
MAX_RECORDS      = 2000   # safety cap for DataFirst catalog pagination
PAGE_SIZE        = 100    # results per catalog page (DataFirst)
SCRAPER_WORKERS  = 2      # only 2 sources now — run in parallel

# ── CIS study number range ─────────────────────────────────────────────────────
# CIS studies are numbered sequentially since 1963 (~1 to 3600+).
# Probe this range to discover which studies have accessible documents.
# Reduce CIS_STUDY_END or narrow the range to limit probe time.
CIS_STUDY_START = int(os.getenv("CIS_STUDY_START", "2000"))
CIS_STUDY_END   = int(os.getenv("CIS_STUDY_END",   "3600"))

# ── Search terms (used for logging / future filtering) ─────────────────────────
QDA_SEARCH_TERMS = [
    # REFI-QDA standard
    "qdpx",
    "refi-qda",
    "qdc",
    # QDA tools
    "NVivo",
    "ATLAS.ti",
    "MAXQDA",
    "QDA Miner",
    "Quirkos",
    "Dedoose",
    # General qualitative
    "qualitative data analysis",
    "CAQDAS",
    "interview study",
    "interview transcript",
    "focus group",
    "ethnographic",
    "qualitative research data",
]

# ── File type groups ───────────────────────────────────────────────────────────

# Highest priority — QDA files (small, rare, high research value)
# REFI-QDA standard:   .qdpx (project exchange), .qdc (codebook exchange)
# NVivo:               .nvp (<=11), .nvpx (12+)
# ATLAS.ti:            .atlproj (8+), .atlcb (Cloud)
# MAXQDA:              .mx18/.mx19/.mx20/.mx22 (versioned), .mxd (legacy)
# QDA Miner:           .qdp (legacy), .qlt (Lite 3.0+)
# f4analyse:           .f4a
# Quirkos:             .quirkos
# Transana:            .tns
# Generic:             .qda
# Spec: https://www.qdasoftware.org/
QDA_EXTENSIONS = {
    ".qdpx", ".qdc", ".qde",               # REFI-QDA (project, codebook, internal XML)
    ".qda",                                 # generic
    ".nvp", ".nvpx",                        # NVivo
    ".atlproj", ".atlcb",                   # ATLAS.ti
    ".mx18", ".mx19", ".mx20", ".mx22", ".mxd",  # MAXQDA
    ".qdp", ".qlt",                         # QDA Miner / QDA Miner Lite
    ".f4a",                                 # f4analyse
    ".quirkos",                             # Quirkos
    ".tns",                                 # Transana
}

# Medium priority — text documents (transcripts, articles)
TEXT_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".rtf", ".txt", ".odt", ".epub", ".html",
}

# Structured exports from QDA tools
STRUCTURED_EXTENSIONS = {
    ".xlsx", ".xls", ".csv", ".ods", ".json", ".xml",
}

# Large media — metadata collected but NOT downloaded by default
MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",   # audio
    ".mp4", ".avi", ".mov", ".mkv", ".webm",   # video
}

# Everything we want to record in the metadata DB
ALL_WANTED_EXTENSIONS = (
    QDA_EXTENSIONS | TEXT_EXTENSIONS | STRUCTURED_EXTENSIONS | MEDIA_EXTENSIONS
)

# ── Download scope (controls which files are actually saved to disk) ────────────
#
#   "qda-only"  → only QDA files downloaded  (DEFAULT — safe, small)
#   "text"      → QDA files + PDFs/transcripts
#   "all"       → everything except media
#
# Audio/video are NEVER downloaded automatically regardless of scope.
# They are always recorded in metadata so the URL is preserved.
#
DOWNLOAD_SCOPE = os.getenv("DOWNLOAD_SCOPE", "qda-only")

DOWNLOAD_EXTENSIONS_BY_SCOPE = {
    "qda-only": QDA_EXTENSIONS,
    "text":     QDA_EXTENSIONS | TEXT_EXTENSIONS | STRUCTURED_EXTENSIONS,
    "all":      QDA_EXTENSIONS | TEXT_EXTENSIONS | STRUCTURED_EXTENSIONS,
}

# ── Storage budget ─────────────────────────────────────────────────────────────
STORAGE_BUDGET_MB  = int(os.getenv("STORAGE_BUDGET_MB", "2048"))  # 2 GB default
MAX_FILE_SIZE_MB   = int(os.getenv("MAX_FILE_SIZE_MB",  "100"))   # skip files > 100 MB

# License checking is handled centrally in src/license_checker.py
