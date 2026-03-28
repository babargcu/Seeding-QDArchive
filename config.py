"""
Central configuration for the Seeding QDArchive pipeline.

Active sources (2):
    DataFirst (UCT, South Africa), CIS (Spain).

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

# ── Optional API tokens (set in .env for higher rate limits / auth) ────────────
ZENODO_TOKEN             = os.getenv("ZENODO_TOKEN",             "")
HARVARD_DATAVERSE_TOKEN  = os.getenv("HARVARD_DATAVERSE_TOKEN",  "")  # harvard.edu instances only
DATAVERSENO_TOKEN        = os.getenv("DATAVERSENO_TOKEN",        "")  # dataverse.no
QDR_TOKEN                = os.getenv("QDR_TOKEN",                "")  # data.qdr.syr.edu
OSF_TOKEN                = os.getenv("OSF_TOKEN",                "")
FIGSHARE_TOKEN           = os.getenv("FIGSHARE_TOKEN",           "")

# Legacy alias — kept so existing .env files with DATAVERSE_TOKEN still work
DATAVERSE_TOKEN = os.getenv("DATAVERSE_TOKEN", HARVARD_DATAVERSE_TOKEN)

# ── Scraper settings ───────────────────────────────────────────────────────────
REQUEST_TIMEOUT  = 30     # seconds per HTTP request
REQUEST_DELAY    = 1.0    # seconds between requests (be polite to servers)
MAX_RECORDS      = 200    # max records per search term per source (API scrapers)
PAGE_SIZE        = 25     # results per API page
SCRAPER_WORKERS  = 8      # parallel source scrapers

# ── Search terms ───────────────────────────────────────────────────────────────
QDA_SEARCH_TERMS = [
    # REFI-QDA standard file formats
    "qdpx", "refi-qda", "qdc",
    # QDA software names
    "NVivo", "ATLAS.ti", "MAXQDA", "QDA Miner", "Quirkos", "Dedoose",
    "f4analyse", "Transana",
    # Key file extensions (some repositories index filenames/descriptions)
    "nvpx", "atlproj", "mqda",
    # Qualitative research methods and data types
    "qualitative data analysis", "CAQDAS",
    "interview study", "interview transcript",
    "focus group", "ethnographic",
    "qualitative research data", "qualitative interview",
    "oral history", "grounded theory",
    "thematic analysis", "discourse analysis",
    "narrative research", "qualitative coding",
]

# ── File type groups ───────────────────────────────────────────────────────────

# Highest priority — QDA files (small, rare, high research value)
# Sources:
#   REFI-QDA standard:  https://www.qdasoftware.org/
#   MAXQDA file types:  https://www.maxqda.com/help/technical-data-and-information/file-management
#   NVivo:              https://lumivero.com/products/nvivo/
#   ATLAS.ti:           https://atlasti.com/
#   QDA Miner:          https://provalisresearch.com/products/qualitative-data-analysis-software/
QDA_EXTENSIONS = {
    # REFI-QDA standard (.qdpx = ZIP bundle; .qdc = codebook XML; .qde = internal project XML)
    ".qdpx", ".qdc", ".qde",

    # NVivo (Lumivero) — .nvp = NVivo ≤11 (Windows); .nvpx = NVivo 12+
    ".nvp", ".nvpx",

    # ATLAS.ti — .atlproj/.atlasproj = 8+ project bundle; .atlcb = Cloud; .hpr7 = v7 legacy
    ".atlproj", ".atlasproj", ".atlcb", ".hpr7",

    # MAXQDA — current formats
    ".mqda",                                # current project (Windows + macOS)
    ".mqex",                                # Exchange file (current)
    ".mqtc",                                # TeamCloud project
    # MAXQDA — versioned project files (newest → oldest)
    ".mx24",                                # MAXQDA 24
    ".mex24",                               # MAXQDA 24 Exchange
    ".mx22",                                # MAXQDA 2022
    ".mex22",                               # MAXQDA 2022 Exchange
    ".mx20",                                # MAXQDA 2020
    ".mx18",                                # MAXQDA 2018
    ".mx12",                                # MAXQDA 12
    ".mx11",                                # MAXQDA 11 (macOS)
    ".mx5",                                 # MAXQDA 11 (Windows)
    ".mx4",                                 # MAXQDA 10
    ".mx3",                                 # MAXQDA 2007
    ".mx2",                                 # MAXQDA 2
    ".mxd",                                 # legacy data file (pre-2018, unofficial)

    # QDA Miner / QDA Miner Lite (Provalis Research)
    ".ppj", ".pprj",                        # QDA Miner project formats
    ".qdp",                                 # QDA Miner 1.x–4.x
    ".qlt",                                 # QDA Miner Lite 3.0+

    # f4analyse / f4x (audiotranskription.de)
    ".f4a",

    # Quirkos
    ".quirkos",

    # Transana
    ".tns",

    # Generic catch-all
    ".qda",
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

# ── CIS (Centro de Investigaciones Sociológicas) ──────────────────────────────
# Study number range to probe.  CIS numbers are sequential integers; the
# scraper HEAD-requests each number to discover which ones exist.
CIS_STUDY_START = int(os.getenv("CIS_STUDY_START", "2500"))
CIS_STUDY_END   = int(os.getenv("CIS_STUDY_END",   "3900"))

# License checking is handled centrally in src/license_checker.py
