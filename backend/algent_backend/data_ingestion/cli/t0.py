"""
``t0`` — produce the t0 discovery pool from its toggleable source channels.

This is the one command that *builds* a t0 end to end (the ``pool`` command only
consolidates already-written artifacts). It runs the same ``ensure_t0`` the rail
calls, so you can test t0 — and each individual channel — by hand, picking which
sources to spend on. For the ordinary path (discovery through to a published
article) use ``newsroom run``; this command is the channel-level tool underneath it.

Channels: ``gkg`` (free GDELT net), ``beats`` (the addressable beat registry, kept
current by a rotating free DOC sweep — the diversity channel), ``markets``
(Polymarket), ``x`` (X API), ``science`` (curated journal / research feeds).
Progress prints to stderr; one JSON summary to stdout.

The beat rotation re-sweeps only the stalest slice, so a t0 close behind another
costs nothing. ``ALGENT_BEATS_REFRESH=0`` serves the sheet without refreshing it.

    python -m algent_backend.cli ingest t0                       # default channels
    python -m algent_backend.cli ingest t0 --force --menu        # fresh pool + numbered menu
    python -m algent_backend.cli ingest t0 --channels gkg,x      # just GKG + X
    python -m algent_backend.cli ingest t0 --channels x --force  # test X alone

This is where discovery STARTS. There is no separate "discovery agent" to launch
first — the retired ``general_discovery`` used to look like one, and running it
before a sweep 429s GDELT and empties the beat channel. See ``docs/guides/newsroom-pipeline.md``.
"""

from __future__ import annotations

import argparse

from ._shared import print_json, progress

# Channel names for the --channels help text. Kept as a literal here (not imported
# from pipeline) so this module — pulled in by cli/__init__ — never imports pipeline
# at load time; pipeline imports cli._shared, so a top-level import would cycle.
_CHANNEL_NAMES = "gkg,beats,markets,x,science"


def add_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("t0", help="build the t0 discovery pool (toggleable channels)")
    parser.add_argument(
        "--channels",
        help=f"comma list of {_CHANNEL_NAMES} (default: env ALGENT_T0_CHANNELS, else all of them)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="rebuild even if a fresh pool exists (sets fresh-minutes to 0)",
    )
    parser.add_argument(
        "--menu", action="store_true",
        help="also print the pool as a numbered menu on stderr, for picking items by number",
    )
    parser.set_defaults(handler=run)


def print_menu(pool: dict, *, out) -> None:
    """Print the pool as one stable numbered list — the thing an operator picks from.

    Numbering runs across the WHOLE pool in pool order, not per channel: a pick is
    "item 74", and that has to mean the same item to the person reading and to any
    command consuming the numbers. Channel headers are annotations inside that one
    sequence, never a restart of it.

    Labels are never truncated. Non-English labels show English first (from
    ``signals.label_en``) with the original on the next line.
    """
    from algent_backend.data_ingestion.newsroom.discovery.label_english import (
        format_menu_label,
    )

    items = pool.get("items") or []
    by_channel: dict[str, list[tuple[int, dict]]] = {}
    for n, item in enumerate(items, 1):
        by_channel.setdefault(str(item.get("channel") or "?"), []).append((n, item))

    print(f"\n=== T0 MENU — {len(items)} items ===", file=out)
    for channel, entries in by_channel.items():
        print(f"\n-- {channel} ({len(entries)}) --", file=out)
        for n, item in entries:
            pillar = (item.get("pillars") or ["-"])[0]
            cryst = "[c] " if (item.get("signals") or {}).get("crystallized") else ""
            display, original = format_menu_label(item)
            missing = (item.get("signals") or {}).get("label_en_missing")
            suffix = " [needs EN]" if missing and not original else ""
            print(f"{n:4}. ({pillar}) {cryst}{display}{suffix}", file=out)
            if original:
                print(f"       orig: {original}", file=out)
    print(file=out)


def run(args: argparse.Namespace) -> int:
    # Imported here (not at module top) to avoid a pipeline<->cli import cycle.
    from ..newsroom.discovery.pipeline import (
        DEFAULT_FRESH_MINUTES,
        ensure_t0,
        resolve_channels,
    )

    channels = set(args.channels.split(",")) if args.channels else None
    chans = resolve_channels(channels)
    progress(f"[t0] building with channels: {', '.join(sorted(chans))}")

    pool, path = ensure_t0(
        channels=chans,
        fresh_minutes=0 if args.force else DEFAULT_FRESH_MINUTES,
        on_progress=progress,
    )
    if args.menu:
        import sys
        print_menu(pool, out=sys.stderr)   # stderr, so stdout stays one clean JSON document

    print_json({
        "channels": sorted(chans),
        "item_count": pool.get("item_count"),
        "by_channel": pool.get("by_channel"),
        "by_pillar": pool.get("by_pillar"),
        "pool_path": path,
    })
    return 0
