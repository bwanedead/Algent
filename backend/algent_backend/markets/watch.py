"""
The mirror's WATCH-SET: every market something of ours depends on, so its outcome gets recorded however the sweep's filters treat it.

The sweep keeps the most liquid in-window markets that map to a theater we cover; a bot, though, may forecast or trade a market outside that (a thin or far-dated one),
and a lab question may name one. A forecast on a market the store never held can never be scored. So the mirror also fetches, BY ID, every market that:

* any strategy forecast (``bot_forecasts``) or the desk forecast (``forecasts``),
* any book traded (``decisions``, every book) or the rule book traded (``trades``),
* any resting limit order was placed on (``resting_orders``),
* any experiment-lab question is built on (``questions/*.json``, ``source = market:<id>``: the prospective lab's questions are live markets that must resolve).

The mirror keeps each such market until it resolves. This module only NAMES the ids (free, read-only); ``mirror.refresh`` does the fetching, bounded by
``flags.WATCH_ENABLED`` and ``flags.WATCH_MAX_FETCH``. The lab's store is read straight from disk by the variable and default the lab itself uses
(``experiment/store.py``), not imported: the lab stays isolated from this package.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import store

LAB_ENV = "ALGENT_EXPERIMENT_STORE"


def lab_market_ids() -> set[str]:
    """Market ids of the experiment lab's questions (``source`` = ``market:<id>``). No lab store, or an unreadable file, is no ids."""
    root = Path(os.environ.get(LAB_ENV) or "experiment_store") / "questions"
    ids: set[str] = set()
    try:
        files = list(root.glob("*.json"))
    except OSError:
        return ids
    for f in files:
        try:
            src = json.loads(f.read_text(encoding="utf-8")).get("source", "")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(src, str) and src.startswith("market:"):
            ids.add(src.split(":", 1)[1])
    return ids


def watched() -> dict[str, set[str]]:
    """Market id -> why it is watched (``forecast`` / ``traded`` / ``rested`` / ``lab``)."""
    out: dict[str, set[str]] = {}
    for why, ids in (("forecast", [f.market_id for f in store.bot_forecasts()] + [f.market_id for f in store.forecasts()]),
                     ("traded", [d.market_id for d in store.decisions(None)] + [t.market_id for t in store.trades()]),
                     ("rested", [o.market_id for o in store.resting_events()]), ("lab", sorted(lab_market_ids()))):
        for mid in ids:
            if mid:
                out.setdefault(str(mid), set()).add(why)
    return out
