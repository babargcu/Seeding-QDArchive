# Data Sources for QDA / Qualitative Data Seeding

## Implemented in pipeline

| Source | URL | API | License notes | Status |
|---|---|---|---|---|
| **Zenodo** | https://zenodo.org/ | Public REST API | SPDX ids; CC variants well-documented | ✅ Implemented |
| **Dryad** | https://datadryad.org/ | Public REST API v2 | All datasets CC0 by policy | ✅ Implemented |
| **Harvard Dataverse** | https://dataverse.harvard.edu | Public REST API | Varies; checked per record | ✅ Implemented |
| **DataverseNO** | https://dataverse.no/ | Public REST API (same as Dataverse) | Varies; checked per record | ✅ Implemented |
| **QDR Syracuse** | https://data.qdr.syr.edu/ | Public REST API (same as Dataverse) | Varies; checked per record | ✅ Implemented |
| **OSF** | https://osf.io/ | Public API v2 | Many projects lack a license — those are skipped | ✅ Implemented |
| **Figshare** | https://figshare.com/ | Public REST API v2 | CC BY default; checked per record | ✅ Implemented |
| **DANS EASY** | https://easy.dans.knaw.nl/ | OAI-PMH (standard) | Varies; dc:rights field checked | ✅ Implemented |

## Requires registration / access agreement

| Source | URL | Access | Notes |
|---|---|---|---|
| **UK Data Service** | https://ukdataservice.ac.uk/ | Free registration | Qualitative-specific collection; Nesstar API; some open datasets |
| **Qualidata Network** | https://www.qualidatanet.com/en/ | Network of European archives | Directory — no direct download API; links to member archives |
| **Qualiservice** | https://www.qualiservice.org/ | Registration required | German qualitative data archive; part of Qualidata Network |
| **QualiBi** | https://www.qualidatanet.com/de/ | Contact required | German qualitative research network |
| **ICPSR** | https://www.icpsr.umich.edu/ | Free registration | Large US social science archive; API key needed |
| **AUSSDA** | https://aussda.at/ | Registration required | Austrian Social Science Data Archive |
| **GESIS** | https://www.gesis.org/ | Varies | German social science data; some open |

## How to add UK Data Service (manual steps)

1. Register free at https://ukdataservice.ac.uk/
2. Browse qualitative collections at https://ukdataservice.ac.uk/learning-hub/qualitative-data/
3. Datasets with open access are marked; download metadata CSV from the catalogue
4. Import the CSV into the pipeline DB using `src/database.py:insert_record()`

## License policy (enforced in code)

| License type | Decision |
|---|---|
| Any Creative Commons (CC0, CC BY, CC BY-SA, CC BY-NC, CC BY-ND, and NC/ND combinations) | ✅ ACCEPT |
| Open Data Commons (ODC-BY, ODbL, PDDL) | ✅ ACCEPT |
| Public Domain / Open Government Licence | ✅ ACCEPT |
| Data Licence Germany (DL-DE) | ✅ ACCEPT |
| Empty / missing license | ❌ SKIP — treated as proprietary |
| "All rights reserved" or proprietary text | ❌ SKIP |
| Unrecognised text | ❌ SKIP |
