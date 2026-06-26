"""
``ensure_t0`` — produce (or reuse) the t0 discovery pool programmatically.

So a discovery *run* can source its own t0 instead of a human/agent running the
ingest commands by hand. Reuses a recent pool if one exists (GKG publishes every
15 min, so a pool a few minutes old is current); otherwise fetches the latest GKG
batch, builds the insights, and consolidates the pool — all free (GDELT bulk), all
narrated through ``on_progress`` so the caller can surface it in a run timeline.

Velocity comes from the rolling memory, which persists across runs, so even the
fast (no-warmup) path sharpens over repeated runs.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.data_ingestion.cli._shared import (
    beats_dir,
    insights_dir,
    latest_file,
    memory_dir,
    pool_dir,
    prune_files,
)

from ..sources import gdelt_gkg
from ..sources.prediction_markets import fetch_polymarket
from ..sources.x_grok_cli import fetch_x_grok
from .insights import build_insights
from .memory import load_memory, save_memory
from .pool import build_pool
from .report import BeatSheet

DEFAULT_FRESH_MINUTES = 20  # a pool newer than this is current (GKG is 15-min)
_KEEP = 1

# The toggleable t0 source channels. ``gkg`` is the free deterministic net (the
# base); ``beats`` reuses a DOC sweep from disk; ``markets`` and ``x`` are extra
# signals fetched live. X (Grok CLI) is slow (~2-3 min) and spends subscription
# quota, so it's OFF by default — opt in per run, see ``resolve_channels``.
ALL_CHANNELS = ("gkg", "beats", "markets", "x")
DEFAULT_CHANNELS = frozenset({"gkg", "beats", "markets"})
_ENV_CHANNELS = "ALGENT_T0_CHANNELS"  # comma-separated override, e.g. "gkg,markets,x"

ProgressFn = Callable[[str], None]


def resolve_channels(channels: set[str] | frozenset[str] | None) -> frozenset[str]:
    """Pick the active t0 channels: explicit arg → ``ALGENT_T0_CHANNELS`` → default."""
    if channels is not None:
        chosen = {c.strip().lower() for c in channels if c.strip()}
    else:
        env = os.environ.get(_ENV_CHANNELS, "")
        chosen = {c.strip().lower() for c in env.split(",") if c.strip()} if env else set(DEFAULT_CHANNELS)
    valid = chosen & set(ALL_CHANNELS)
    return frozenset(valid or DEFAULT_CHANNELS)


def ensure_t0(
    *, source: str = "gdelt_gkg", fresh_minutes: float = DEFAULT_FRESH_MINUTES,
    channels: set[str] | frozenset[str] | None = None,
    on_progress: ProgressFn | None = None,
) -> tuple[dict[str, Any], str]:
    """Return ``(pool_dict, pool_path)`` — a fresh-enough t0, producing it if needed."""
    say = on_progress or (lambda _m: None)
    chans = resolve_channels(channels)

    existing = latest_file(pool_dir(), "pool_*.json")
    if existing is not None and _age_minutes(existing) <= fresh_minutes:
        say(f"reusing current t0 pool ({_age_minutes(existing):.0f} min old)")
        return json.loads(existing.read_text(encoding="utf-8")), str(existing)

    say(f"building t0 (channels: {', '.join(sorted(chans))})…")
    report = _build_insights(source, say) if "gkg" in chans else None
    pool, path = _build_pool(report, chans, say)
    return pool, path


def _build_insights(source: str, say: ProgressFn):
    say("fetching latest GKG batch (download)…")
    batch_id, records = gdelt_gkg.fetch_latest()
    say(f"GKG batch {batch_id}: {len(records)} records")
    memory = load_memory(source, memory_dir())
    report, counts = build_insights(records, source=source, batch_id=batch_id, memory=memory)
    out = insights_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{source}_{batch_id}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    save_memory(memory.with_batch(batch_id, counts), memory_dir())
    prune_files(out, f"{source}_*.json", keep=_KEEP)
    say(f"insights: {len(report.candidates)} candidates across {len(report.by_language)} languages")
    return report


def _build_pool(report, chans: frozenset[str], say: ProgressFn) -> tuple[dict[str, Any], str]:
    sheet = _load_beats(say) if "beats" in chans else None
    markets = _fetch_markets(say) if "markets" in chans else []
    x_hits = _fetch_x(say) if "x" in chans else []
    pool = build_pool(report, sheet, markets, x_hits)
    out = pool_dir()
    out.mkdir(parents=True, exist_ok=True)
    stamp = report.batch_id if report is not None else datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    path = out / f"pool_{stamp}.json"
    path.write_text(pool.model_dump_json(indent=2), encoding="utf-8")
    prune_files(out, "pool_*.json", keep=_KEEP)
    say(f"t0 pool ready: {pool.item_count} items  {pool.by_channel}")
    return pool.model_dump(), str(path)


def _load_beats(say: ProgressFn) -> BeatSheet | None:
    beats_latest = latest_file(beats_dir(), "beats_*.json")
    if beats_latest is None:
        return None
    try:
        return BeatSheet.model_validate_json(beats_latest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fetch_markets(say: ProgressFn) -> list[dict]:
    try:
        say("fetching prediction markets (free, novel signal)…")
        markets = fetch_polymarket(limit=25)
        say(f"prediction markets: {len(markets)} active leads")
        return markets
    except Exception:  # noqa: BLE001 — a market-API hiccup must not block t0
        say("prediction markets: skipped (fetch failed)")
        return []


def _fetch_x(say: ProgressFn) -> list[dict]:
    from ..sources.x_grok_cli import resolve_lanes

    lanes = resolve_lanes(None)
    say(f"fetching X via Grok CLI across {len(lanes)} lanes ({', '.join(lanes)}) — subscription, slow…")
    hits = fetch_x_grok()  # best-effort fan-out: returns [] on total failure
    say(f"X (grok): {len(hits)} topics across lanes" if hits else "X (grok): none (skipped/failed)")
    return hits


def _age_minutes(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 60.0
