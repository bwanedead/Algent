"""
Shared mechanics for the data-ingestion CLI: JSON output, on-disk locations,
and the source registry.

Mechanics only — nothing here interprets data. The registry is the single place
that knows which sources exist and what each can do (retrieve raw, and/or be
digested), so adding a source is a one-line change here.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from ..news_production.sources import gdelt_gkg, gdelt_ngrams

# backend/ — parents: [cli, data_ingestion, algent_backend, backend]
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_OUTPUT_ENV = "ALGENT_INGESTION_DIR"

# Every retrievable source, by id. A source module exposes ``fetch_latest_raw``.
SOURCES = {
    gdelt_gkg.SOURCE_ID: gdelt_gkg,
    gdelt_ngrams.SOURCE_ID: gdelt_ngrams,
}

# Sources that additionally have a processing (digest) pipeline today.
DIGESTABLE = {gdelt_gkg.SOURCE_ID}


def ingestion_dir() -> Path:
    override = os.environ.get(_OUTPUT_ENV)
    return Path(override) if override else _BACKEND_DIR / "ingestion_data"


def raw_dir() -> Path:
    return ingestion_dir() / "raw"


def digests_dir() -> Path:
    return ingestion_dir() / "digests"


def insights_dir() -> Path:
    return ingestion_dir() / "insights"


def samples_dir() -> Path:
    return ingestion_dir() / "samples"


def beats_dir() -> Path:
    return ingestion_dir() / "beats"


def pool_dir() -> Path:
    return ingestion_dir() / "pool"


def latest_file(directory: Path, pattern: str) -> Path | None:
    """The newest file matching `pattern` in `directory` (by name), or None."""
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern))
    return files[-1] if files else None


def memory_dir() -> Path:
    """Rolling cross-batch state (small aggregates). Retained, not one-in-one-out."""
    return ingestion_dir() / "memory"


def print_json(payload: object) -> None:
    """Print the command's single JSON document (UTF-8, never crashes on cp1252)."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


def progress(message: str) -> None:
    """Live progress line to STDERR — keeps stdout's single-JSON contract intact.

    The slow ingest steps (paced sweeps, multi-batch warmup) are otherwise silent
    for minutes; this narrates them so a run is observably alive, not hung.
    """
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.write(message.rstrip() + "\n")
    sys.stderr.flush()


# -- retention ----------------------------------------------------------------
#
# Slim by default: keep only the newest `keep` batches per source so test runs
# don't accumulate junk. Batch ids are sortable timestamps, so a name sort puts
# oldest first. We may retain more (or archive) later — that's just a bigger
# `keep`. Best-effort: pruning never raises.


def prune_raw_batches(source: str, *, keep: int) -> list[str]:
    """Keep the newest `keep` raw batch dirs for a source; remove older ones."""
    src_dir = raw_dir() / source
    if not src_dir.exists():
        return []
    dirs = [p for p in src_dir.iterdir() if p.is_dir()]
    return _prune(dirs, keep, lambda p: shutil.rmtree(p, ignore_errors=True))


def prune_files(directory: Path, pattern: str, *, keep: int) -> list[str]:
    """Keep the newest `keep` files matching `pattern` in `directory`; remove older."""
    if not directory.exists():
        return []
    files = list(directory.glob(pattern))
    return _prune(files, keep, lambda p: p.unlink(missing_ok=True))


def prune_digest_files(source: str, *, keep: int) -> list[str]:
    """Keep the newest `keep` digest files for a source; remove older ones."""
    return prune_files(digests_dir(), f"{source}_*.json", keep=keep)


def _prune(paths: list[Path], keep: int, remove: Callable[[Path], None]) -> list[str]:
    if keep < 1:
        return []
    stale = sorted(paths)[:-keep]  # name sort = oldest first; drop all but newest `keep`
    for path in stale:
        remove(path)
    return [path.name for path in stale]
