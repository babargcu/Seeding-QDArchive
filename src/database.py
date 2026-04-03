"""
SQLite metadata database — normalized schema for the QDArchive seeding pipeline.

Tables
------
repositories  — known source repositories (seeded on first run)
projects      — one row per research project / dataset
files         — one row per file within a project
keywords      — one keyword per row (normalised from pipe-separated strings)
person_role   — one person+role pair per row
licenses      — one license per row per project

Primary rule: data is stored exactly as received — no cleaning or normalisation
              of content values.  Quality issues are resolved in a later step.

Schema field notes
------------------
projects.download_date         — timestamp when the project was first scraped
projects.download_method       — 'API-CALL' | 'SCRAPING'
files.status                   — 'PENDING' | 'SUCCESS' | 'FAILED' | 'SKIPPED'
person_role.role               — 'AUTHOR' | 'DEPOSITOR' | 'CONTRIBUTOR' | 'UNKNOWN'
"""

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

import config


# ── Repository seed data ───────────────────────────────────────────────────────
# (id, name, top-level URL, download_method)
# Extend this list when new sources are added.
_REPOSITORIES: list[tuple] = [
    (1,  "Zenodo",                 "https://zenodo.org",                    "API-CALL"),
    (2,  "Dryad",                  "https://datadryad.org",                 "API-CALL"),
    (3,  "DANS EASY",              "https://easy.dans.knaw.nl",             "API-CALL"),
    (4,  "OSF",                    "https://osf.io",                        "API-CALL"),
    (5,  "Figshare",               "https://figshare.com",                  "API-CALL"),
    (6,  "Harvard Dataverse",      "https://dataverse.harvard.edu",         "API-CALL"),
    (7,  "Harvard Murray Archive", "https://dataverse.harvard.edu",         "API-CALL"),
    (8,  "DataverseNO",            "https://dataverse.no",                  "API-CALL"),
    (9,  "QDR Syracuse",           "https://data.qdr.syr.edu",              "API-CALL"),
    (10, "DataFirst",              "https://www.datafirst.uct.ac.za",       "SCRAPING"),
    (11, "CIS",                    "https://www.cis.es",                    "SCRAPING"),
]

# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS repositories (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    url             TEXT    NOT NULL DEFAULT '',
    download_method TEXT    NOT NULL DEFAULT 'API-CALL'
);

CREATE TABLE IF NOT EXISTS projects (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    query_string                TEXT,
    repository_id               INTEGER NOT NULL REFERENCES repositories(id),
    repository_url              TEXT    NOT NULL DEFAULT '',
    project_url                 TEXT    NOT NULL DEFAULT '',
    version                     TEXT,
    title                       TEXT    NOT NULL DEFAULT '',
    description                 TEXT,
    language                    TEXT,
    doi                         TEXT,
    upload_date                 TEXT,
    download_date               TEXT    NOT NULL,
    download_repository_folder  TEXT    NOT NULL DEFAULT '',
    download_project_folder     TEXT    NOT NULL DEFAULT '',
    download_version_folder     TEXT,
    download_method             TEXT    NOT NULL DEFAULT 'API-CALL',
    UNIQUE(repository_id, project_url)
);

CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER NOT NULL REFERENCES projects(id),
    file_name    TEXT    NOT NULL DEFAULT '',
    file_type    TEXT    NOT NULL DEFAULT '',
    download_url TEXT    NOT NULL DEFAULT '',
    file_size    INTEGER DEFAULT 0,
    local_path   TEXT,
    status       TEXT    NOT NULL DEFAULT 'PENDING',
    UNIQUE(project_id, download_url)
);

CREATE TABLE IF NOT EXISTS keywords (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    keyword    TEXT    NOT NULL,
    UNIQUE(project_id, keyword)
);

CREATE TABLE IF NOT EXISTS person_role (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    name       TEXT    NOT NULL,
    role       TEXT    NOT NULL DEFAULT 'UNKNOWN',
    UNIQUE(project_id, name, role)
);

CREATE TABLE IF NOT EXISTS licenses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    license    TEXT    NOT NULL,
    UNIQUE(project_id, license)
);
"""


# ── Connection ────────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    for stmt in _DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)

    # Seed known repositories (INSERT OR IGNORE — safe to call repeatedly)
    conn.executemany(
        "INSERT OR IGNORE INTO repositories (id, name, url, download_method) VALUES (?,?,?,?)",
        _REPOSITORIES,
    )
    conn.commit()
    return conn


# ── Public insert entry point ─────────────────────────────────────────────────

def insert_record(conn: sqlite3.Connection, record: dict) -> int | None:
    """
    Insert one scraped record into the normalised schema.

    Handles project deduplication, then inserts file, keywords, persons,
    and license rows.  Returns the new files.id, or None if it is an exact
    duplicate (same project + download_url).
    """
    project_url = record.get("source_link", "")
    if not project_url:
        return None

    source = record.get("source", "")
    repo_id, repo_url, dl_method = _get_or_create_repository(conn, source)

    project_id = _insert_or_get_project(conn, record, repo_id, repo_url, dl_method)
    if project_id is None:
        return None

    file_id = _insert_file(conn, project_id, record)

    # Always (re-)insert these — INSERT OR IGNORE handles duplicates cheaply
    _insert_keywords(conn, project_id, record.get("keywords", ""))
    _insert_persons(conn, project_id, record.get("authors", ""),       "AUTHOR")
    _insert_persons(conn, project_id, record.get("uploader_name", ""), "DEPOSITOR")
    _insert_license(conn, project_id, record.get("license", ""))

    conn.commit()
    return file_id


# ── Download-phase helpers ────────────────────────────────────────────────────

def mark_downloaded(conn: sqlite3.Connection, file_id: int, local_path: str):
    """Mark a file as successfully downloaded and record its local path."""
    conn.execute(
        "UPDATE files SET status='SUCCESS', local_path=? WHERE id=?",
        (local_path, file_id),
    )
    conn.commit()


def get_pending_files(
    conn: sqlite3.Connection,
    downloadable_exts: set[str],
    sources: list[str] | None = None,
) -> list:
    """
    Return all pending files whose type matches the download scope,
    prioritising QDA files.

    Args:
        sources: Optional list of repository names to restrict downloads to.
                 None = all sources.
    """
    ext_csv   = ", ".join(f"'{e.lstrip('.')}'" for e in downloadable_exts)
    qda_csv   = ", ".join(f"'{e.lstrip('.')}'" for e in config.QDA_EXTENSIONS)
    media_csv = ", ".join(f"'{e.lstrip('.')}'" for e in config.MEDIA_EXTENSIONS)

    source_filter = ""
    params: list = []
    if sources:
        placeholders = ", ".join("?" * len(sources))
        source_filter = f"AND r.name IN ({placeholders})"
        params.extend(sources)

    rows = conn.execute(f"""
        SELECT
            f.id,
            f.download_url,
            f.file_name,
            f.file_type,
            p.download_repository_folder,
            p.download_project_folder
        FROM   files f
        JOIN   projects p ON f.project_id = p.id
        JOIN   repositories r ON p.repository_id = r.id
        WHERE  f.status = 'PENDING'
          AND  f.download_url != ''
          AND  f.file_type IN ({ext_csv})
          {source_filter}
        ORDER BY
               CASE WHEN f.file_type IN ({qda_csv}) THEN 0 ELSE 1 END,
               f.id
    """, params).fetchall()

    media_count = conn.execute(
        f"SELECT COUNT(*) FROM files WHERE file_type IN ({media_csv})"
    ).fetchone()[0]

    return rows, media_count


# ── Export & stats ────────────────────────────────────────────────────────────

def export_csv(conn: sqlite3.Connection, path: Path | None = None) -> Path:
    """Export a denormalised flat view of all tables joined together."""
    path = path or (
        config.REPORT_DIR / f"metadata_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    query = """
        SELECT
            p.id                        AS project_id,
            p.query_string,
            r.name                      AS repository,
            r.url                       AS repository_url,
            p.project_url,
            p.title,
            p.description,
            p.language,
            p.doi,
            p.upload_date,
            p.download_date,
            p.download_method,
            p.download_repository_folder,
            p.download_project_folder,
            p.download_version_folder,
            f.id                        AS file_id,
            f.file_name,
            f.file_type,
            f.download_url,
            f.file_size,
            f.local_path,
            f.status                    AS file_status,
            GROUP_CONCAT(DISTINCT l.license)                              AS licenses,
            GROUP_CONCAT(DISTINCT k.keyword)                              AS keywords,
            GROUP_CONCAT(DISTINCT CASE WHEN pr.role='AUTHOR'    THEN pr.name END) AS authors,
            GROUP_CONCAT(DISTINCT CASE WHEN pr.role='DEPOSITOR' THEN pr.name END) AS depositor
        FROM   projects p
        JOIN   repositories r   ON p.repository_id = r.id
        LEFT JOIN files f       ON f.project_id = p.id
        LEFT JOIN licenses l    ON l.project_id = p.id
        LEFT JOIN keywords k    ON k.project_id = p.id
        LEFT JOIN person_role pr ON pr.project_id = p.id
        GROUP BY f.id
        ORDER BY p.id, f.id
    """
    df = pd.read_sql_query(query, conn)
    df.to_csv(path, index=False)
    return path


def stats(conn: sqlite3.Connection) -> dict:
    cur = conn.execute("""
        SELECT
            (SELECT COUNT(*)               FROM projects)                   AS total,
            (SELECT COUNT(*)               FROM files WHERE status='SUCCESS') AS downloaded,
            (SELECT COUNT(DISTINCT repository_id) FROM projects)            AS sources,
            (SELECT COUNT(DISTINCT license) FROM licenses)                  AS licenses
    """)
    return dict(cur.fetchone())


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_or_create_repository(
    conn: sqlite3.Connection, source_name: str
) -> tuple[int, str, str]:
    """Return (id, url, download_method) for a source, inserting if unknown."""
    row = conn.execute(
        "SELECT id, url, download_method FROM repositories WHERE name=?", (source_name,)
    ).fetchone()
    if row:
        return row["id"], row["url"], row["download_method"]

    # Unknown source — insert with sensible defaults
    conn.execute(
        "INSERT OR IGNORE INTO repositories (name, url, download_method) VALUES (?,?,?)",
        (source_name, "", "SCRAPING"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, url, download_method FROM repositories WHERE name=?", (source_name,)
    ).fetchone()
    return row["id"], row["url"], row["download_method"]


def _insert_or_get_project(
    conn: sqlite3.Connection,
    record: dict,
    repo_id: int,
    repo_url: str,
    dl_method: str,
) -> int | None:
    project_url    = record.get("source_link", "")
    project_folder = _extract_project_folder(project_url, record.get("local_dir", ""))
    repo_folder    = _repo_folder(record.get("source", ""))
    now            = datetime.now(timezone.utc).isoformat()

    try:
        cur = conn.execute(
            """
            INSERT INTO projects (
                query_string, repository_id, repository_url, project_url,
                version, title, description, language, doi, upload_date,
                download_date,
                download_repository_folder, download_project_folder,
                download_version_folder, download_method
            ) VALUES (?,?,?,?, ?,?,?,?,?,?, ?,?,?, ?,?)
            """,
            (
                record.get("query_string", ""),
                repo_id,
                repo_url,
                project_url,
                record.get("version", ""),
                record.get("title", ""),
                (record.get("description") or "")[:4000],
                record.get("language", ""),
                _extract_doi(record),
                record.get("date_published", ""),
                now,
                repo_folder,
                project_folder,
                record.get("version", ""),   # version folder = version string
                dl_method,
            ),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # Project already exists
        row = conn.execute(
            "SELECT id FROM projects WHERE repository_id=? AND project_url=?",
            (repo_id, project_url),
        ).fetchone()
        return row["id"] if row else None


def _insert_file(conn: sqlite3.Connection, project_id: int, record: dict) -> int | None:
    try:
        cur = conn.execute(
            """
            INSERT INTO files (project_id, file_name, file_type, download_url, file_size, status)
            VALUES (?,?,?,?,?,'PENDING')
            """,
            (
                project_id,
                record.get("file_name", ""),
                record.get("file_type", ""),
                record.get("download_url", ""),
                int(record.get("file_size", 0) or 0),
            ),
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # exact duplicate (same project + download_url)


def _insert_keywords(conn: sqlite3.Connection, project_id: int, raw: str):
    for kw in (raw or "").split("|"):
        kw = kw.strip()
        if kw:
            conn.execute(
                "INSERT OR IGNORE INTO keywords (project_id, keyword) VALUES (?,?)",
                (project_id, kw),
            )


def _insert_persons(conn: sqlite3.Connection, project_id: int, raw: str, role: str):
    for name in (raw or "").split("|"):
        name = name.strip()
        if name:
            conn.execute(
                "INSERT OR IGNORE INTO person_role (project_id, name, role) VALUES (?,?,?)",
                (project_id, name, role),
            )


def _insert_license(conn: sqlite3.Connection, project_id: int, license_str: str):
    if license_str and license_str.strip():
        conn.execute(
            "INSERT OR IGNORE INTO licenses (project_id, license) VALUES (?,?)",
            (project_id, license_str.strip()),
        )


# ── URL / path utilities ──────────────────────────────────────────────────────

_DOI_RE = re.compile(r"(10\.\d{4,}/[^\s,;\"'<>\]]+)")
_SKIP_PATH_PARTS = {
    "search", "catalog", "index.php", "records", "dataset.xhtml",
    "dataverse", "api", "access", "datafile",
}


def _extract_doi(record: dict) -> str:
    """Return a fully-qualified DOI URL if one can be found in the record."""
    doi = record.get("doi", "")
    if doi:
        return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    for field in ("source_link", "download_url", "license_url"):
        m = _DOI_RE.search(record.get(field, ""))
        if m:
            return f"https://doi.org/{m.group(1)}"
    return ""


def _extract_project_folder(project_url: str, local_dir: str) -> str:
    """Return the folder name to use for this project's downloads."""
    if local_dir:
        return _safe_name(local_dir)[:120]
    if not project_url:
        return "unknown"
    parts = [p for p in urlparse(project_url).path.rstrip("/").split("/") if p]
    for part in reversed(parts):
        if part not in _SKIP_PATH_PARTS:
            return _safe_name(part)[:120]
    return _safe_name(parts[-1])[:120] if parts else "unknown"


def _repo_folder(source_name: str) -> str:
    """Return a filesystem-safe folder name for a repository."""
    return re.sub(r"[^a-z0-9]+", "-", source_name.lower()).strip("-")


def _safe_name(name: str) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    return "".join(c if c in keep else "_" for c in name)
