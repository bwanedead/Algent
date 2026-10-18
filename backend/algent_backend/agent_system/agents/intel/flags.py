"""
Intel desk operator defaults — in-repo hand-switches, same convention as ``newsroom/flags.py``.

Edit the constants here; do not ask the operator to set ``.env`` for them. One-shot override for a single
run: ``ALGENT_<FLAG>`` in the process env (``ALGENT_SWEEP=0``, ``ALGENT_SPOTLIGHT_SECTIONS=0``).
"""

from __future__ import annotations

import os
from typing import NamedTuple


class Edition(NamedTuple):
    n: int
    label: str        # reader-facing: "Part 1 · {label}" / "added {utc} UTC · {cycle}"
    cycle: str        # the news cycle it covers
    utc: str          # HH:MM UTC the scheduler starts it (infra/server/install_schedules.sh reads this)


#: The daily's EDITIONS: the day's report is built in parts, each an APPEND to ONE record (``daily_editions``).
#: Part 1 is the normal run; part 2 re-reads what is new since part 1 and adds sections/updates for it. The times
#: are when the scheduled jobs fire (before the Americas news cycle is mostly in, before Europe/Asia wakes up
#: again); change them here and re-run ``infra/server/install_schedules.sh``. More parts are possible: add a row.
EDITIONS: tuple[Edition, ...] = (
    Edition(1, "Europe/Asia morning", "Europe/Asia", "05:30"),
    Edition(2, "Americas", "Americas", "17:30"),
)


#: The AI daily (`intel daily --domain ai --research`, one part a day) as a PAID scheduled job. ON: operator-authorised 2026-10-18. To stop it, flip this one
#: constant to False, push, and re-run `infra/server/install_schedules.sh` (it reads `newsroom schedule times`, which lists the job only when True).
AI_DAILY_SCHEDULED = True
#: When it fires (UTC, HH:MM): after the AI sources' crawl and benchmark collection, and clear of geopolitics part 1 (05:30) and the markets daily (07:30).
AI_DAILY_UTC = "09:00"


def edition_info(n: int) -> Edition:
    """The edition numbered ``n`` (a row of ``EDITIONS``); unknown numbers get a neutral label, never an error."""
    return next((e for e in EDITIONS if e.n == n), Edition(n, f"Part {n}", "", ""))


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

#: Ceiling on visuals per edition run (an append edition plans its own sections' visuals under the same ceiling).
#: The planner's honest answer is usually fewer; this is a spend/attention bound.
VISUALS_MAX_PER_DAY = 3

#: Which coding harness draws them: "" = the analytics default (``ALGENT_ANALYTICS_HARNESS``, else grok), or
#: "grok" / "codex". Both are subscription-funded CLIs on the server, so a visual costs no API dollars.
VISUALS_HARNESS = ""

#: Interactive 3D scenes (``scene3d.py``): the planner may propose the ``scene3d`` visual kind when 3D explains
#: better than any flat picture. Counts against ``VISUALS_MAX_PER_DAY``. False = the planner is told it cannot.
SCENE3D_ENABLED = True

#: Native interactive forms - timelines, map stories, networks, flow maps, tracker comparisons (``native_forms.py``): the site draws them from a validated data
#: spec, one structured model call each, no harness. Counts against ``VISUALS_MAX_PER_DAY``. False = the planner
#: cannot choose them (these forms are never routed to the static-chart harness either way).
NATIVE_FORMS_ENABLED = True

#: Size limits the scene validator enforces (mobile budget): objects, and total vertices across coastlines,
#: terrain, outlines and lines. The contract's own hard ceilings are higher; these are the operating bounds.
SCENE3D_MAX_OBJECTS = 60
SCENE3D_MAX_VERTICES = 3000

#: Whether a scene may draw a thing's size from a PUBLIC specification the planner named (`source_hint`) rather
#: than from the day's own facts. The numbers then come from the model's reading of that source and are shown
#: under the picture with the source named; set False to restrict scenes to the day's facts.
SCENE3D_PUBLIC_SPECS = True

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


def scene3d_enabled() -> bool:
    raw = os.environ.get("ALGENT_SCENE3D")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in _FALSEY
    return bool(SCENE3D_ENABLED)


def native_forms_enabled() -> bool:
    raw = os.environ.get("ALGENT_NATIVE_FORMS")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in _FALSEY
    return bool(NATIVE_FORMS_ENABLED)


def scene3d_limits() -> tuple[int, int]:
    return max(1, int(SCENE3D_MAX_OBJECTS)), max(1, int(SCENE3D_MAX_VERTICES))


def scene3d_public_specs() -> bool:
    return bool(SCENE3D_PUBLIC_SPECS)
