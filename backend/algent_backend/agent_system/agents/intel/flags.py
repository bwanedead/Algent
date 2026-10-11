"""
Intel desk operator defaults — in-repo hand-switches, same convention as ``newsroom/flags.py``.

Edit the constants here; do not ask the operator to set ``.env`` for them. One-shot override for a single
run: ``ALGENT_<FLAG>`` in the process env (``ALGENT_SWEEP=0``, ``ALGENT_SPOTLIGHT_SECTIONS=0``).
"""

from __future__ import annotations

import os

#: The daily's "Around the world" sweep (``sweep.py``): ONE house-model call over material the desk already
#: holds for free, writing a short region-grouped digest of what the focus sections do not cover. False
#: skips the call (the daily is then exactly what it was).
SWEEP_ENABLED = True

#: How many EXTRA researched sections the sweep's Spotlight may add to a run. ONE, by design: each researched
#: section is slow and paid, and the point of the Spotlight is depth on one under-covered thing, not a second
#: focus. It only runs with ``--research`` (the nomination itself is free, part of the sweep call). 0 = off.
#: Raise it only as a deliberate budget decision.
SPOTLIGHT_SECTIONS = 1

#: Ad-hoc visuals for the daily (``visuals.py``): ONE planning call over the day's sourced material proposes
#: 0-3 visuals (any code-renderable form), each drawn by the article analytics harness. False = none.
VISUALS_ENABLED = True

#: Ceiling on visuals per day. The planner's honest answer is usually fewer; this is a spend/attention bound.
VISUALS_MAX_PER_DAY = 3

#: Which coding harness draws them: "" = the analytics default (``ALGENT_ANALYTICS_HARNESS``, else grok), or
#: "grok" / "codex". Both are subscription-funded CLIs on the server, so a visual costs no API dollars.
VISUALS_HARNESS = ""

_FALSEY = ("0", "false", "no", "off")


def visuals_enabled() -> bool:
    raw = os.environ.get("ALGENT_VISUALS")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in _FALSEY
    return bool(VISUALS_ENABLED)


def visuals_max() -> int:
    raw = os.environ.get("ALGENT_VISUALS_MAX")
    try:
        return max(0, int(raw)) if raw is not None and raw.strip() != "" else max(0, int(VISUALS_MAX_PER_DAY))
    except ValueError:
        return max(0, int(VISUALS_MAX_PER_DAY))


def visuals_harness() -> str:
    return (os.environ.get("ALGENT_VISUALS_HARNESS") or VISUALS_HARNESS or "").strip().lower()


def sweep_enabled() -> bool:
    raw = os.environ.get("ALGENT_SWEEP")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in _FALSEY
    return bool(SWEEP_ENABLED)


def spotlight_sections() -> int:
    raw = os.environ.get("ALGENT_SPOTLIGHT_SECTIONS")
    try:
        return max(0, int(raw)) if raw is not None and raw.strip() != "" else max(0, int(SPOTLIGHT_SECTIONS))
    except ValueError:
        return max(0, int(SPOTLIGHT_SECTIONS))
