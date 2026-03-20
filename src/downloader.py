"""
File downloader with resume support, size cap, and storage budget tracking.

Budget behaviour:
    - If a single file is larger than the per-file cap  → SKIP that file, continue
    - If a single file would push total over budget      → SKIP that file, continue
    - If budget is fully used up (used >= budget)        → STOP all downloads
"""

import logging
from pathlib import Path

import requests
from tqdm import tqdm

import config

logger = logging.getLogger(__name__)


class StorageBudgetExceeded(Exception):
    """Raised only when the total budget is completely used up."""
    pass


class Downloader:
    """
    Manages downloads against a shared storage budget.

    Usage:
        dl = Downloader(budget_mb=200)
        path = dl.download(url, dest_dir, filename)
    """

    def __init__(self, budget_mb: int | None = None):
        self.budget_mb    = budget_mb or config.STORAGE_BUDGET_MB
        self.budget_bytes = self.budget_mb * 1024 * 1024
        self.used_bytes   = 0
        self.session      = requests.Session()
        self.session.headers["User-Agent"] = (
            "SeedingQDArchive/1.0 (research pipeline; "
            "github.com/your-org/Seeding-QDArchive)"
        )

    @property
    def remaining_mb(self) -> float:
        return (self.budget_bytes - self.used_bytes) / 1024 / 1024

    def download(self, url: str, dest_dir: Path, filename: str) -> Path | None:
        """
        Download `url` to `dest_dir / filename`.

        Returns:
            Path  — download succeeded
            None  — skipped (too large, or would exceed budget) or failed
        Raises:
            StorageBudgetExceeded — budget is fully exhausted, stop all downloads
        """
        # Budget fully exhausted → stop everything
        if self.used_bytes >= self.budget_bytes:
            raise StorageBudgetExceeded(
                f"Storage budget of {self.budget_mb} MB fully used."
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / _safe_name(filename)

        # Probe remote file size
        remote_size = self._probe_size(url)
        max_bytes   = config.MAX_FILE_SIZE_MB * 1024 * 1024

        # Per-file size cap — skip, don't stop
        if remote_size and remote_size > max_bytes:
            logger.warning(
                "Skipping %s — %.1f MB exceeds per-file limit of %d MB",
                filename, remote_size / 1024 / 1024, config.MAX_FILE_SIZE_MB,
            )
            return None

        # File would push total over budget — skip this file, try next ones
        if remote_size and (self.used_bytes + remote_size) > self.budget_bytes:
            logger.warning(
                "Skipping %s — %.1f MB would exceed remaining budget of %.1f MB",
                filename, remote_size / 1024 / 1024, self.remaining_mb,
            )
            return None

        # Already fully downloaded — skip
        if dest.exists() and remote_size and dest.stat().st_size == remote_size:
            logger.debug("Already downloaded: %s", dest.name)
            return dest

        try:
            with self.session.get(url, stream=True, timeout=config.REQUEST_TIMEOUT) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length", 0))

                with open(dest, "wb") as fh, tqdm(
                    total=total or None,
                    unit="B",
                    unit_scale=True,
                    desc=dest.name[:45],
                    leave=False,
                ) as bar:
                    for chunk in resp.iter_content(chunk_size=8192):
                        fh.write(chunk)
                        bar.update(len(chunk))
                        self.used_bytes += len(chunk)

            logger.info(
                "Downloaded: %s  (used %.1f / %d MB)",
                dest.name, self.used_bytes / 1024 / 1024, self.budget_mb,
            )
            return dest

        except Exception as exc:
            logger.warning("Failed to download %s: %s", url, exc)
            if dest.exists():
                dest.unlink(missing_ok=True)
            return None

    def _probe_size(self, url: str) -> int:
        try:
            resp = self.session.head(
                url, timeout=config.REQUEST_TIMEOUT, allow_redirects=True
            )
            return int(resp.headers.get("Content-Length", 0))
        except Exception:
            return 0


def _safe_name(name: str) -> str:
    keep = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789._- ()"
    )
    return "".join(c if c in keep else "_" for c in name)[:200]
