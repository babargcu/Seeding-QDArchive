# Data Sources for QDA / Qualitative Data Seeding

## Active in pipeline

### REST API scrapers

| Source | URL | Scraper | API | License notes |
|---|---|---|---|---|
| **Zenodo** | https://zenodo.org/ | `zenodo.py` | Public REST API | SPDX ids; CC variants well-documented |
| **Dryad** | https://datadryad.org/ | `dryad.py` | Public REST API v2 | All datasets CC0 by policy |
| **OSF** | https://osf.io/ | `osf.py` | Public API v2 | Projects without a license are skipped |
| **Figshare** | https://figshare.com/ | `figshare.py` | Public REST API v2 | CC BY default; checked per record |

### Dataverse instances (all use `dataverse.py`)

| Source | Base URL | Subtree | Notes |
|---|---|---|---|
| **Harvard Dataverse** | https://dataverse.harvard.edu | — | Largest general Dataverse; license varies per record |
| **Harvard Murray Archive** | https://dataverse.harvard.edu | `mra` | Henry A. Murray Research Archive; 900+ qualitative files |
| **DataverseNO** | https://dataverse.no | — | Norwegian national research data repository |
| **QDR Syracuse** | https://data.qdr.syr.edu | — | Qualitative Data Repository at Syracuse University |

### OAI-PMH scrapers

| Source | URL | Scraper | OAI endpoint |
|---|---|---|---|
| **DANS EASY** | https://dans.knaw.nl/en/ | `dans.py` | https://easy.dans.knaw.nl/oai/ |

### HTML-scraped sources

| Source | URL | Scraper | Notes |
|---|---|---|---|
| **DataFirst (UCT/SADA)** | https://datafirst.uct.ac.za/ | `datafirst.py` | South African NADA catalog; 594+ datasets |

---

## Inactive scrapers (files kept, not wired into pipeline)

| Scraper file | Source | Notes |
|---|---|---|
| `cis.py` | CIS Spain | Liferay portal; removed from active pipeline |

---

## Search terms (`config.QDA_SEARCH_TERMS`)

API-based scrapers (Zenodo, Dryad, OSF, Figshare, all Dataverse instances) search
every source with each of these terms. OAI-PMH (DANS) and HTML scrapers (DataFirst)
harvest all records and filter locally.

**REFI-QDA formats:** `qdpx` · `refi-qda` · `qdc`

**QDA tools:** `NVivo` · `ATLAS.ti` · `MAXQDA` · `QDA Miner` · `Quirkos` · `Dedoose` · `f4analyse` · `Transana`

**File extensions:** `nvpx` · `atlproj` · `mqda`

**Qualitative methods:** `qualitative data analysis` · `CAQDAS` · `interview study` · `interview transcript` · `focus group` · `ethnographic` · `qualitative research data` · `qualitative interview` · `oral history` · `grounded theory` · `thematic analysis` · `discourse analysis` · `narrative research` · `qualitative coding`

---

## License policy (`src/license_checker.py`)

| License type | Decision |
|---|---|
| Any Creative Commons (CC0, CC BY, CC BY-SA, CC BY-NC, CC BY-ND, combinations) | ✅ ACCEPT |
| Open Data Commons (ODC-BY, ODbL, PDDL) | ✅ ACCEPT |
| Public Domain / Open Government Licence | ✅ ACCEPT |
| Data Licence Germany (DL-DE) | ✅ ACCEPT |
| Empty / missing license | ❌ SKIP |
| "All rights reserved" or proprietary | ❌ SKIP |
| Unrecognised text | ❌ SKIP |

> **DataFirst exception:** all records are collected regardless of license.
> The license is recorded in the DB for manual review but is not used as a filter.

---

## Adding a new Dataverse instance

In `src/pipeline.py`, add one line to `_build_scrapers()`:

```python
DataverseScraper("https://your-dataverse.org", "Display Name", config.DATAVERSE_TOKEN)
# With subtree (sub-collection):
DataverseScraper("https://dataverse.harvard.edu", "My Sub-Archive", config.DATAVERSE_TOKEN, subtree="alias")
```

## Adding a new OAI-PMH source

Copy `src/scrapers/dans.py` and adapt the endpoint URL, `source_name`, and keyword filter.
