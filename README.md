# Seeding QDArchive — Data Acquisition

A pipeline that finds, catalogues, and archives open **qualitative research data** and **QDA files** from the web to seed the QDArchive repository.

- **Qualitative data** — interview transcripts, research articles, audio/video
- **QDA files** — structured annotation files from tools like NVivo, ATLAS.ti, MAXQDA (`.qdpx`, `.qdc`, `.nvp`, `.atlproj`, …)

This repository implements **Part 1: Data Acquisition**.

---

## How it works

```
Scrape metadata (parallel)     Download files        Export
──────────────────────────     ──────────────        ──────
Zenodo          ──┐            QDA files only        metadata.db
Dryad           ──┤            (.qdpx, .nvp,         └──▶ reports/*.csv
Harvard DV      ──┤──▶ DB ───▶  .atlproj, …)
DataverseNO     ──┤            Audio/video:
QDR Syracuse    ──┤            URL saved only,
OSF             ──┤            never downloaded
Figshare        ──┤
DANS EASY       ──┘
```

**Default behaviour (safe, recommended):**

| File type | Action |
|---|---|
| QDA files (`.qdpx`, `.qdc`, `.nvp`, `.atlproj`, `.mx*`, …) | **Downloaded** — small and high-value |
| PDFs, transcripts, spreadsheets | Metadata + URL saved only |
| Audio / Video | Metadata + URL saved only — **never downloaded** |

- Storage hard-stops at **2 GB** by default
- Records with no open license are **skipped entirely**

---

## Prerequisites

- **Python 3.10 or higher** — check with:
  ```cmd
  python --version
  ```
  If below 3.10, download from [python.org](https://www.python.org/downloads/). During install, tick **"Add Python to PATH"**.

- **Internet connection** — the pipeline calls public APIs

---

## Installation

Open **Command Prompt**, then:

```cmd
cd "C:\Users\Babar\Desktop\Seeding-QDArchive"

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

Your prompt should show `(.venv)` after activation.

---

## Testing (run in this order)

### Test A — Sanity check, 1–2 minutes

Scrapes only Zenodo, no files downloaded:

```cmd
python main.py --no-download --sources Zenodo
```

**Check:**
- No import errors in the output
- Log lines like `[Zenodo] Searching: 'qdpx'`
- A CSV file appears in `reports/`
- Open the CSV in Excel — it should have rows with titles, licenses, and URLs

---

### Test B — Verify the database

```cmd
python -c "import sqlite3; conn = sqlite3.connect('data/metadata.db'); print(conn.execute('SELECT source, COUNT(*) FROM datasets GROUP BY source').fetchall())"
```

Expected output: something like `[('Zenodo', 34)]`

---

### Test C — Add more sources, still no download, 5–15 minutes

```cmd
python main.py --no-download --sources Zenodo Dryad Figshare
```

---

### Test D — First real download, 50 MB cap

```cmd
python main.py --no-scrape --budget 50
```

Uses records already in the DB. Downloads QDA files only. Check `data/downloads/` for files.

---

### Test E — Full run (when confident)

```cmd
python main.py --budget 200
```

---

## All CLI options

```cmd
# Metadata only — zero disk usage
python main.py --no-download

# Download QDA + PDFs/transcripts
python main.py --download-scope text

# Restrict to specific sources
python main.py --sources Zenodo Dryad OSF

# Set storage cap in MB
python main.py --budget 500

# Re-export CSV without scraping or downloading
python main.py --no-scrape --no-download

# Full list of options
python main.py --help
```

**Available sources:** Zenodo, Dryad, Harvard Dataverse, DataverseNO, QDR Syracuse, OSF, Figshare, DANS EASY

---

## What to check after a run

| Location | What it contains |
|---|---|
| `reports/metadata_*.csv` | All records — open in Excel to inspect |
| `data/downloads/` | Downloaded QDA files, organised by source |
| `pipeline.log` | Full log with errors and warnings |

---

## Project structure

```
Seeding-QDArchive/
├── main.py                    # Entry point / CLI
├── config.py                  # All settings (paths, budgets, search terms)
├── requirements.txt
├── .env.example               # Copy to .env for optional API keys
│
├── src/
│   ├── license_checker.py     # Strict open-license verification
│   ├── database.py            # SQLite DB + CSV export
│   ├── downloader.py          # File downloader (budget-aware, resumable)
│   ├── pipeline.py            # Orchestrates scrape → store → download → export
│   └── scrapers/
│       ├── base.py            # Abstract base scraper
│       ├── zenodo.py          # Zenodo public API
│       ├── dryad.py           # Dryad public API (all CC0)
│       ├── dataverse.py       # Configurable Dataverse scraper
│       │                      #   used for: Harvard DV, DataverseNO, QDR Syracuse
│       ├── osf.py             # OSF public API
│       ├── figshare.py        # Figshare public API
│       └── dans.py            # DANS EASY (OAI-PMH protocol)
│
├── docs/
│   ├── file_types.csv         # All known QDA / qualitative file extensions
│   └── sources.md             # Source catalogue with access notes
│
├── data/
│   └── downloads/             # Downloaded QDA files (gitignored)
│
└── reports/                   # Auto-generated CSV metadata exports
```

---

## Data sources

| Source | URL | API | Key needed |
|---|---|---|---|
| Zenodo | https://zenodo.org | Public REST | No (optional) |
| Dryad | https://datadryad.org | Public REST | No |
| Harvard Dataverse | https://dataverse.harvard.edu | Public REST | No (optional) |
| DataverseNO | https://dataverse.no | Public REST | No |
| QDR Syracuse | https://data.qdr.syr.edu | Public REST | No |
| OSF | https://osf.io | Public REST | No (optional) |
| Figshare | https://figshare.com | Public REST | No (optional) |
| DANS EASY | https://easy.dans.knaw.nl | OAI-PMH | No |

See `docs/sources.md` for additional sources (UK Data Service, ICPSR, Qualiservice) that require free registration.

---

## Database schema

One row per file found. Exported as CSV to `reports/` after each run.

| Column | Description |
|---|---|
| `source` | Source name |
| `source_link` | URL to the dataset page |
| `download_url` | Direct file URL |
| `title` | Dataset title |
| `description` | Abstract |
| `authors` | Pipe-separated authors |
| `date_published` | ISO date |
| `license` | License name (e.g. `CC BY 4.0`) |
| `license_url` | Full license URL |
| `file_type` | Extension without dot |
| `file_name` | Original filename |
| `file_size` | Size in bytes |
| `project_scope` | `QDA` / `Qualitative` / `Media` / `Other` |
| `keywords` | Pipe-separated tags |
| `language` | Language code |
| `local_path` | Relative path after download |
| `downloaded` | `1` if file saved to disk |
| `download_date` | Timestamp of download |

---

## License policy

Only records with a recognised open license are collected:

| License type | Decision |
|---|---|
| Any Creative Commons (CC0, CC BY, CC BY-SA, CC BY-NC, CC BY-ND, …) | ✅ Accept |
| Open Data Commons (ODC-BY, ODbL, PDDL) | ✅ Accept |
| Public Domain / Open Government Licence | ✅ Accept |
| Empty / missing license | ❌ Skip — treated as proprietary |
| Unrecognised text | ❌ Skip |

---

## Common errors and fixes

| Error | Fix |
|---|---|
| `ModuleNotFoundError` | Make sure `.venv` is active, then `pip install -r requirements.txt` |
| `python` not recognised | Use `python3`, or reinstall Python and tick "Add to PATH" |
| `ConnectionError` on a source | That source is temporarily down — re-run later; other sources continue |
| Empty CSV after run | No open-licensed records found — check `pipeline.log` for `SKIP` lines |
| Permission error on `data/` | Run Command Prompt as normal user (not admin) |

---

## Optional API keys

API keys are not required but increase rate limits for heavy use.
Copy `.env.example` to `.env` and fill in any you have:

```cmd
copy .env.example .env
```

---

## Git tags

- `part-1-release` — Data acquisition pipeline complete
