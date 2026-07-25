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
from .insights import build_insights
from .memory import load_memory, save_memory
from .pool import build_pool
from .report import BeatSheet

DEFAULT_FRESH_MINUTES = 20  # a pool newer than this is current (GKG is 15-min)
_KEEP = 1

# The toggleable t0 source channels. ``gkg`` is the free deterministic net (the
# base); ``beats`` keeps the addressable beat registry fresh on a rotating sweep
# (free DOC; the diversity channel — see ``beat_refresh``); ``markets`` and ``x``
# are extra signals fetched live; ``science`` is the curiosity channel and the only one
# that does not run through GDELT (see ``sources.science_feeds`` — every registry query
# shares one DOC endpoint, so a single throttle silenced science entirely).
# X primary path is the **X API** (same surface as
# api.x.com/mcp): prefer **News stories** (platform-clustered headlines), NOT
# WOEID trends and NOT a fixed AI/account roster. Grok CLI optional. ON by default.
# Disable: ALGENT_T0_CHANNELS=gkg,beats,markets or no bearer.
ALL_CHANNELS = ("gkg", "beats", "markets", "x", "science")
DEFAULT_CHANNELS = frozenset({"gkg", "beats", "markets", "x", "science"})
_ENV_CHANNELS = "ALGENT_T0_CHANNELS"  # comma-separated override, e.g. "gkg,markets"
# How t0 pulls X: ``api`` (default news/stories), ``api+grok``, ``grok`` (legacy).
_ENV_X_VIA = "ALGENT_X_T0_VIA"

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
    science = _fetch_science(say) if "science" in chans else []
    # When X is on, shrink wire/market mass so novelty/spectrum leads stay visible
    # in the chooser menu (not 40 GKG + 25 markets drowning ~20 X).
    gkg_limit = markets_limit = None
    if x_hits:
        gkg_limit = _cap_env("ALGENT_T0_GKG_CAP", 45, lo=10, hi=120)
        markets_limit = _cap_env("ALGENT_T0_MARKETS_CAP", 16, lo=5, hi=40)
        say(
            f"rebalance with X on: GKG≤{gkg_limit}, markets≤{markets_limit}, "
            f"X={len(x_hits)} (raise/lower via ALGENT_T0_GKG_CAP / ALGENT_T0_MARKETS_CAP)"
        )
    # The sweep is capped unconditionally (unlike gkg/markets, which only rebalance
    # when X is on) because a swept registry is ~40 queries × 25 records. But the cap
    # is a *payload* bound, not an editorial one: a long menu is the point — it is how
    # the operator sees each cycle what we are prone to, and the research/drafting
    # bandwidth this feeds is meant to grow into it. Echo suppression already strips
    # the redundancy, so a high cap buys distinct leads rather than more of the same.
    beats_limit = None
    if sheet is not None:
        beats_limit = _cap_env("ALGENT_T0_BEATS_CAP", 90, lo=4, hi=300)
        say(f"sweep: ≤{beats_limit} pool items, echoes dropped (ALGENT_T0_BEATS_CAP)")
    science_limit = _cap_env("ALGENT_T0_SCIENCE_CAP", 24, lo=4, hi=80) if science else None
    pool = build_pool(
        report, sheet, markets, x_hits, science,
        gkg_limit=gkg_limit, markets_limit=markets_limit, beats_limit=beats_limit,
        science_limit=science_limit,
    )
    # Semantic finisher: rewrite to event sentences / drop non-events (cheap LLM).
    try:
        from .crystallize import crystallize_pool
        pool, cryst = crystallize_pool(pool, on_progress=say)
        if cryst.mode != "off" and cryst.dropped:
            say(
                f"crystallize summary: mode={cryst.mode} kept={cryst.kept} "
                f"dropped={cryst.dropped} usd~{cryst.estimated_usd:.4f}"
            )
    except Exception as exc:  # noqa: BLE001 — never block t0 on crystallizer
        say(f"crystallize: skipped ({str(exc)[:80]})")
    out = pool_dir()
    out.mkdir(parents=True, exist_ok=True)
    stamp = report.batch_id if report is not None else datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    path = out / f"pool_{stamp}.json"
    path.write_text(pool.model_dump_json(indent=2), encoding="utf-8")
    prune_files(out, "pool_*.json", keep=_KEEP)
    by = pool.by_channel
    x_share = (by.get("x", 0) / pool.item_count) if pool.item_count else 0.0
    say(f"t0 pool ready: {pool.item_count} items  {by}  x_share={x_share:.0%}")
    if x_hits:
        from collections import Counter
        src = Counter(str(h.get("source") or "?") for h in x_hits)
        say(f"X band breakdown: {dict(src)}")
    return pool.model_dump(), str(path)


def _cap_env(name: str, default: int, *, lo: int, hi: int) -> int:
    """A per-channel pool cap from the environment, clamped to a sane range."""
    try:
        return max(lo, min(hi, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def _load_beats(say: ProgressFn) -> BeatSheet | None:
    """The sweep channel: load the standing sheet, drop what's stale, refresh the rotation.

    This is the half of discovery that goes *looking* instead of listening. GKG, X and
    markets all measure loudness, so on their own they re-find whatever is already
    everywhere; the sweep casts targeted queries into corners of the corpus the
    loudness channels never reach. Left as a pure disk read it decays into nothing
    (and it did — a dead sheet made every pool wire-and-trend only), so the sheet is
    refreshed here, a stalest-slice at a time. Free (GDELT DOC) and paced; opt out
    with ``ALGENT_BEATS_REFRESH=0``.
    """
    from . import beat_refresh

    sheet = _read_beat_sheet()
    if beat_refresh.refresh_enabled():
        try:
            sheet = beat_refresh.refresh_sheet(sheet, on_progress=say)
        except Exception as exc:  # noqa: BLE001 — a source hiccup must not sink t0
            say(f"beats: refresh failed ({str(exc)[:80]}) — serving what's current")
            sheet = beat_refresh.prune_stale(sheet)
        else:
            _write_beat_sheet(sheet, say)
    else:
        # Age guard applies either way: a stale sheet contributes nothing rather
        # than folding month-old articles into t0 as today's news.
        sheet = beat_refresh.prune_stale(sheet)
    if sheet is None:
        say("beats: no current sheet (channel contributes nothing this cycle)")
    return sheet


def _read_beat_sheet() -> BeatSheet | None:
    beats_latest = latest_file(beats_dir(), "beats_*.json")
    if beats_latest is None:
        return None
    try:
        return BeatSheet.model_validate_json(beats_latest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_beat_sheet(sheet: BeatSheet | None, say: ProgressFn) -> None:
    """Persist the merged sheet so the rotation carries across runs."""
    if sheet is None:
        return
    try:
        out = beats_dir()
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        (out / f"beats_{stamp}.json").write_text(
            sheet.model_dump_json(indent=2), encoding="utf-8"
        )
        prune_files(out, "beats_*.json", keep=_KEEP)
    except OSError as exc:
        say(f"beats: could not persist sheet ({str(exc)[:60]})")


def _fetch_science(say: ProgressFn) -> list[dict]:
    """The curiosity channel: edited science feeds, free, independent of GDELT."""
    try:
        from ..sources.science_feeds import FEEDS, fetch_science

        say(f"fetching science feeds ({len(FEEDS)} sources, free)…")
        hits = fetch_science()
        from collections import Counter
        say(f"science: {len(hits)} items {dict(Counter(h.get('feed') for h in hits))}")
        return hits
    except Exception as exc:  # noqa: BLE001 — a dead feed must not sink t0
        say(f"science: skipped ({str(exc)[:70]})")
        return []


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
    """X into t0: general News + wires + **dedicated AI pulse** (not trends-only).

    General legs stay domain-agnostic. AI labs/people are a *reserved* third slice so
    we keep release/lab eyeballs without making discovery AI-primary. Cap hard.
    Grok only if ``ALGENT_X_T0_VIA=api+grok``.
    """
    via = os.environ.get(_ENV_X_VIA, "api").strip().lower() or "api"
    hits: list[dict] = []

    if via in ("api", "api+grok", "native"):
        from ..sources.x_native import fetch_x_api_discovery, last_cost, resolve_bearer

        if not resolve_bearer():
            say("X (api): skipped — no bearer token (X_BEARER_TOKEN / X_BEARER_KEY)")
        else:
            say("fetching X News + general wires + AI pulse…")
            try:
                api_hits = fetch_x_api_discovery()
            except Exception as exc:  # noqa: BLE001 — X must not sink t0
                say(f"X (api): failed ({str(exc)[:80]})")
                api_hits = []
            hits.extend(api_hits)
            c = last_cost()
            ai_n = sum(1 for h in api_hits if str(h.get("source")) == "x_ai_pulse")
            say(
                f"X (api): {c.get('topics', 0)} hits ({ai_n} ai_pulse), "
                f"{c.get('posts_fetched', 0)} posts, "
                f"~${float(c.get('estimated_usd') or 0):.4f} est. "
                f"(mode={c.get('mode')}, news_reqs={c.get('news_requests', 0)}, "
                f"timelines={c.get('user_timeline_requests', 0)}, "
                f"searches={c.get('search_requests', 0)})"
                if api_hits else "X (api): none"
            )

    if via in ("grok", "api+grok"):
        from ..sources.x_grok_cli import fetch_x_grok, resolve_lanes

        lanes = resolve_lanes(None)
        say(f"fetching X via Grok CLI (supplement) across {len(lanes)} lanes — subscription…")
        try:
            grok_hits = fetch_x_grok()
        except Exception as exc:  # noqa: BLE001
            say(f"X (grok): failed ({str(exc)[:80]})")
            grok_hits = []
        grok_hits = (grok_hits or [])[:10]
        hits.extend(grok_hits)
        say(f"X (grok): {len(grok_hits)} topics" if grok_hits else "X (grok): none")

    if via not in ("api", "api+grok", "native", "grok"):
        say(f"X: unknown ALGENT_X_T0_VIA={via!r} (use api | api+grok | grok); defaulting to api")
        os.environ[_ENV_X_VIA] = "api"
        return _fetch_x(say)

    max_topics = 36
    try:
        max_topics = max(1, min(50, int(os.environ.get("ALGENT_X_MAX_TOPICS", "36"))))
    except ValueError:
        pass
    return hits[:max_topics]


def _age_minutes(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 60.0
