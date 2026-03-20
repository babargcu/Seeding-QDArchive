"""
SQLite metadata database for the QDArchive seeding pipeline.

Schema (one row per file found):

  Required (per spec):
    download_url    — direct URL of the QDA / document file
    download_date   — ISO datetime of last successful download (null until downloaded)
    local_dir       — subdirectory name inside data/downloads/{source}/ (e.g. "doctor-nurse-study-4552r45")
    file_name       — filename on disk (e.g. "main.qdpx")

  Context:
    source          — repository name (e.g. "DataFirst", "CIS")
    source_link     — URL of the dataset/study page

  Study metadata:
    title           — study/dataset title
    description     — abstract
    authors         — pipe-separated research authors
    uploader_name   — person/org who deposited to the repository
    uploader_email  — depositor email (may be empty)
    date_published  — ISO date string

  File info:
    file_type       — extension without dot (e.g. "qdpx", "pdf")
    file_size       — size in bytes (0 if unknown)
    project_scope   — "QDA" | "Qualitative" | "Media" | "Other"

  Extras:
    license         — license name (e.g. "CC BY 4.0")
    license_url     — URL to full license text
    keywords        — pipe-separated keywords
    language        — language code (e.g. "en")
    local_path      — full relative path after download (source + local_dir + file_name)
    downloaded      — 1 if file saved to disk, else 0
    created_at      — row creation timestamp
"""

import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

import config


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- required
    download_url    TEXT    NOT NULL DEFAULT '',
    download_date   TEXT,
    local_dir       TEXT    NOT NULL DEFAULT '',
    file_name       TEXT    NOT NULL DEFAULT '',
    -- context
    source          TEXT,
    source_link     TEXT,
    -- study metadata
    title           TEXT,
    description     TEXT,
    authors         TEXT,
    uploader_name   TEXT,
    uploader_email  TEXT,
    date_published  TEXT,
    -- file info
    file_type       TEXT,
    file_size       INTEGER DEFAULT 0,
    project_scope   TEXT,
    -- extras
    license         TEXT,
    license_url     TEXT,
    keywords        TEXT,
    language        TEXT,
    local_path      TEXT,
    downloaded      INTEGER DEFAULT 0,
    created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, download_url)
);
"""

# Columns added after v1 — applied via ALTER TABLE so existing DBs are upgraded
_MIGRATIONS = [
    "ALTER TABLE datasets ADD COLUMN uploader_name  TEXT;",
    "ALTER TABLE datasets ADD COLUMN uploader_email TEXT;",
    "ALTER TABLE datasets ADD COLUMN local_dir      TEXT NOT NULL DEFAULT '';",
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(_CREATE_SQL)
    conn.commit()
    # Apply any missing columns (idempotent — errors are silently ignored)
    for sql in _MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    return conn


def insert_record(conn: sqlite3.Connection, record: dict) -> int | None:
    """
    Insert a metadata record.
    Returns the new row id, or None if the record already exists
    (duplicate source + download_url).
    """
    cols = [
        "download_url", "local_dir", "file_name",
        "source", "source_link",
        "title", "description",
        "authors", "uploader_name", "uploader_email",
        "date_published",
        "file_type", "file_size", "project_scope",
        "license", "license_url",
        "keywords", "language",
    ]
    row = {c: record.get(c, "") for c in cols}
    row["file_size"] = int(row.get("file_size") or 0)

    placeholders = ", ".join(f":{c}" for c in cols)
    sql = f"""
        INSERT OR IGNORE INTO datasets ({', '.join(cols)})
        VALUES ({placeholders})
    """
    cur = conn.execute(sql, row)
    conn.commit()
    return cur.lastrowid if cur.lastrowid else None


def mark_downloaded(conn: sqlite3.Connection, row_id: int, local_path: str):
    """Set downloaded=1, local_path, and download_date for a row."""
    conn.execute(
        """UPDATE datasets
           SET downloaded=1, local_path=?, download_date=?
           WHERE id=?""",
        (local_path, datetime.utcnow().isoformat(), row_id),
    )
    conn.commit()


def export_csv(conn: sqlite3.Connection, path: Path | None = None) -> Path:
    path = path or (
        config.REPORT_DIR / f"metadata_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    df = pd.read_sql_query("SELECT * FROM datasets ORDER BY id", conn)
    df.to_csv(path, index=False)
    return path


def stats(conn: sqlite3.Connection) -> dict:
    cur = conn.execute("""
        SELECT
            COUNT(*)            AS total,
            SUM(downloaded)     AS downloaded,
            COUNT(DISTINCT source)  AS sources,
            COUNT(DISTINCT license) AS licenses
        FROM datasets
    """)
    return dict(cur.fetchone())
