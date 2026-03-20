"""
Pipeline orchestrator — DataFirst + CIS only.

Sources:
    DataFirst (UCT, South Africa) — NADA catalog HTML scraping
    CIS (Spain) — Liferay portal, document URL probing

Phases:
    1. Scrape  — collect metadata → DB  (all records, license recorded not filtered)
    2. Download — only files matching the chosen scope (default: qda-only)
    3. Export  — write full metadata CSV to reports/

All records are collected regardless of license.
Audio/video: NEVER downloaded — URL always recorded in DB.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
from src.database import get_connection, insert_record, mark_downloaded, export_csv, stats
from src.downloader import Downloader, StorageBudgetExceeded
from src.scrapers.datafirst import DataFirstScraper
from src.scrapers.cis import CISScraper

logger = logging.getLogger(__name__)


def _build_scrapers() -> list:
    return [
        DataFirstScraper(),
        CISScraper(),
    ]


def get_available_sources() -> list[str]:
    return [s.source_name for s in _build_scrapers()]


def run(
    scrape:         bool = True,
    download:       bool = True,
    export:         bool = True,
    sources:        list[str] | None = None,
    download_scope: str | None = None,
    budget_mb:      int | None = None,
) -> dict:
    """
    Run the pipeline.

    Args:
        scrape:         Run metadata-scraping phase.
        download:       Run file-download phase.
        export:         Write CSV to reports/ when done.
        sources:        Restrict to these source names (None = all).
        download_scope: 'qda-only' | 'text' | 'all'
        budget_mb:      Storage cap in MB (overrides config default).

    Returns:
        Stats dict: total, downloaded, sources, licenses.
    """
    scope = download_scope or config.DOWNLOAD_SCOPE
    downloadable_exts = config.DOWNLOAD_EXTENSIONS_BY_SCOPE.get(
        scope, config.QDA_EXTENSIONS
    )

    conn = get_connection()

    # ── Phase 1: Scrape ────────────────────────────────────────────────────────
    if scrape:
        active = [
            s for s in _build_scrapers()
            if not sources or s.source_name in sources
        ]
        logger.info(
            "Scraping %d source(s) with up to %d workers in parallel…",
            len(active), config.SCRAPER_WORKERS,
        )

        def _scrape_one(scraper):
            logger.info("=== [%s] Starting scrape ===", scraper.source_name)
            try:
                return scraper.source_name, scraper.fetch_all()
            except Exception as exc:
                logger.error("[%s] Scraper crashed: %s", scraper.source_name, exc)
                return scraper.source_name, []

        with ThreadPoolExecutor(max_workers=config.SCRAPER_WORKERS) as pool:
            futures = {pool.submit(_scrape_one, s): s for s in active}
            for future in as_completed(futures):
                source_name, records = future.result()
                inserted = sum(1 for r in records if insert_record(conn, r))
                logger.info(
                    "[%s] Done — %d new records inserted (found %d total)",
                    source_name, inserted, len(records),
                )

    # ── Phase 2: Download ──────────────────────────────────────────────────────
    if download:
        ext_csv   = ", ".join(f"'{e.lstrip('.')}'" for e in downloadable_exts)
        qda_csv   = ", ".join(f"'{e.lstrip('.')}'" for e in config.QDA_EXTENSIONS)
        media_csv = ", ".join(f"'{e.lstrip('.')}'" for e in config.MEDIA_EXTENSIONS)

        rows = conn.execute(f"""
            SELECT id, source, download_url, file_name, file_type, local_dir
            FROM   datasets
            WHERE  downloaded = 0
              AND  download_url != ''
              AND  file_type IN ({ext_csv})
            ORDER BY
                   CASE WHEN file_type IN ({qda_csv}) THEN 0 ELSE 1 END,
                   id
        """).fetchall()

        media_count = conn.execute(
            f"SELECT COUNT(*) FROM datasets WHERE file_type IN ({media_csv})"
        ).fetchone()[0]

        budget = budget_mb or config.STORAGE_BUDGET_MB
        logger.info(
            "=== Download phase (scope=%s, budget=%d MB) ===\n"
            "    To download : %d files\n"
            "    Media skipped (URL saved): %d",
            scope, budget, len(rows), media_count,
        )

        downloader = Downloader(budget_mb=budget)

        for row in rows:
            # Structure: data/downloads/{source}/{local_dir}/{file_name}
            study_dir = _safe_dirname(row["local_dir"]) if row["local_dir"] else f"study_{row['id']}"
            dest_dir  = config.DATA_DIR / _safe_dirname(row["source"]) / study_dir
            fname     = row["file_name"] or f"file_{row['id']}.{row['file_type']}"
            try:
                dest = downloader.download(row["download_url"], dest_dir, fname)
                if dest:
                    mark_downloaded(conn, row["id"], str(dest.relative_to(config.BASE_DIR)))
            except StorageBudgetExceeded as exc:
                logger.warning("Budget reached — stopping. %s", exc)
                break
            time.sleep(config.REQUEST_DELAY)

        logger.info(
            "Download done — %.1f MB used of %d MB budget",
            downloader.used_bytes / 1024 / 1024, budget,
        )

    # ── Phase 3: Export CSV ────────────────────────────────────────────────────
    if export:
        csv_path = export_csv(conn)
        logger.info("CSV exported → %s", csv_path)

    result = stats(conn)
    conn.close()
    logger.info(
        "Pipeline complete — total=%d  downloaded=%d  sources=%d  licenses=%d",
        result["total"], result["downloaded"], result["sources"], result["licenses"],
    )
    return result


def _safe_dirname(name: str) -> str:
    keep = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ")
    return "".join(c if c in keep else "_" for c in name).strip()
