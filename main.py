#!/usr/bin/env python3
"""
Seeding QDArchive — Data Acquisition Pipeline
==============================================

Sources: Zenodo, Dryad, OSF, Figshare,
         Harvard Dataverse, Harvard Murray Research Archive,
         DataverseNO, QDR Syracuse,
         DANS EASY, DataFirst (UCT)

Default behaviour (safe for a university project):
    • Scrapes ALL sources for metadata
    • Downloads ONLY QDA files (.qdpx, .nvp, .atlproj, .mx*, …)
    • Audio / video: URL recorded in DB — NEVER downloaded
    • Hard stops at 2 GB storage budget

License rule: any record without a recognised open license is skipped.
              Creative Commons (all variants), ODC, public domain, etc. accepted.
              No license = skipped as proprietary.

Usage:

    # Full run — scrape all, download QDA files only (RECOMMENDED)
    python main.py

    # Metadata only — zero disk usage
    python main.py --no-download

    # Also download PDFs and transcripts
    python main.py --download-scope text

    # Limit to specific sources
    python main.py --sources Zenodo Dryad "QDR Syracuse"

    # Set storage cap (MB)
    python main.py --budget 200

    # Re-export current DB to CSV without scraping/downloading
    python main.py --no-scrape --no-download
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("pipeline.log", encoding="utf-8", delay=False),
    ],
)

from src.pipeline import run, get_available_sources


def main():
    available = get_available_sources()

    parser = argparse.ArgumentParser(
        description="Seeding QDArchive — data acquisition pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-scrape", dest="scrape", action="store_false",
        help="Skip metadata scraping (use existing DB records only)",
    )
    parser.add_argument(
        "--no-download", dest="download", action="store_false",
        help="Skip all file downloads (metadata only run)",
    )
    parser.add_argument(
        "--no-export", dest="export", action="store_false",
        help="Skip CSV export at the end",
    )
    parser.add_argument(
        "--download-scope",
        choices=["qda-only", "text", "all"],
        default="qda-only",
        help=(
            "Which files to actually save to disk (default: qda-only).\n"
            "  qda-only — .qdpx, NVivo, ATLAS.ti, MAXQDA files\n"
            "  text     — QDA + PDFs + transcripts + spreadsheets\n"
            "  all      — all non-media files\n"
            "Audio/video URLs are always recorded but never downloaded."
        ),
    )
    parser.add_argument(
        "--sources", nargs="+", metavar="SOURCE",
        help=f"Restrict to specific sources. Available: {', '.join(available)}",
    )
    parser.add_argument(
        "--budget", type=int, default=None, metavar="MB",
        help="Storage budget in MB (default: 2048 / 2 GB). Use e.g. --budget 200 for safety.",
    )

    args = parser.parse_args()

    # Validate source names
    if args.sources:
        invalid = [s for s in args.sources if s not in available]
        if invalid:
            print(f"ERROR: Unknown sources: {invalid}")
            print(f"Available: {available}")
            sys.exit(1)

    result = run(
        scrape=args.scrape,
        download=args.download,
        export=args.export,
        sources=args.sources,
        download_scope=args.download_scope,
        budget_mb=args.budget,
    )

    print("\n--- Pipeline Summary ---")
    print(f"  Total records in DB  : {result['total']}")
    print(f"  Files downloaded     : {result['downloaded']}")
    print(f"  Unique sources       : {result['sources']}")
    print(f"  Unique licenses      : {result['licenses']}")
    print(f"  Log file             : pipeline.log")
    print(f"  Metadata CSV         : reports/")


if __name__ == "__main__":
    main()
