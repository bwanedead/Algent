"""
``sweep`` — run the targeted beat sweep (the complement to the general GKG net).

Fetches each registered beat via paced DOC API queries and writes a faceted
:class:`BeatSheet` (tagged hits, sliceable downstream by pillar/country). This is
the deterministic "hard-target per niche" coverage: economics, AI, per-country
general events, etc., each fetched on purpose so a niche is never starved.

It is slow by design — the DOC API rate limit forces ~one request every few
seconds, so a full sweep of all beats takes minutes. Use ``--kind`` / ``--limit``
to sweep a subset.

    python -m algent_backend.data_ingestion.cli sweep                 # all beats
    python -m algent_backend.data_ingestion.cli sweep --kind pillar   # pillars only
    python -m algent_backend.data_ingestion.cli sweep --limit 4       # first 4 (testing)
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from ..newsroom.discovery import beats as beats_registry
from ..newsroom.discovery.sweep import run_sweep
from ._shared import beats_dir, print_json, progress, prune_files


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("sweep", help="targeted beat sweep via the DOC API")
    parser.add_argument("--kind", choices=["all", "pillar", "country"], default="all")
    parser.add_argument("--limit", type=int, default=0, help="sweep only the first N beats")
    parser.add_argument("--max-records", type=int, default=25, dest="max_records")
    parser.add_argument("--pace", type=float, default=None, help="seconds between requests")
    parser.add_argument("--keep", type=int, default=1, help="beat sheets to retain (default 1)")
    parser.set_defaults(handler=run)


def _select(kind: str, limit: int) -> list:
    beats = {
        "all": beats_registry.all_beats,
        "pillar": beats_registry.pillar_beats,
        "country": beats_registry.country_beats,
    }[kind]()
    return beats[:limit] if limit else beats


def run(args: argparse.Namespace) -> int:
    targets = _select(args.kind, args.limit)
    progress(f"[sweep] starting {len(targets)} beats (paced; this takes a few minutes)…")

    def _on_progress(done: int, total: int, result) -> None:
        outcome = f"{result.hit_count} hits" if not result.error else f"ERROR: {result.error}"
        progress(f"[sweep] {done}/{total}  {result.beat_id:24} -> {outcome}")

    kwargs = {"max_records": args.max_records, "on_progress": _on_progress}
    if args.pace is not None:
        kwargs["pace_s"] = args.pace
    sheet = run_sweep(targets, **kwargs)
    progress(f"[sweep] done: {sheet.beats_swept} swept, {sheet.beats_failed} failed.")

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    out_dir = beats_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"beats_{stamp}.json"
    path.write_text(sheet.model_dump_json(indent=2), encoding="utf-8")
    purged = prune_files(out_dir, "beats_*.json", keep=args.keep)

    print_json(
        {
            "beats_swept": sheet.beats_swept,
            "beats_failed": sheet.beats_failed,
            "total_hits": sheet.total_hits,
            "sheet_path": str(path),
            "retained": args.keep,
            "purged": purged,
        }
    )
    return 0
