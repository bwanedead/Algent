"""
``views/event/<date>/<theater_id>.json``: the developments of one theater's section on one day, for the development pages (``/intel/events/<date>/<theater>/<n>``).

A development page used to load the whole day's report (up to 800 KB) plus the entity index to show one paragraph and link its actors. The view holds
that section's developments (raw, parsed by the site's Daily parser), the state each actor name resolves to, and the theater's ref.
"""

from __future__ import annotations

from typing import Any

from . import dailies, flags, graph, mentions
from .base import View, make
from .context import ViewContext


def build(ctx: ViewContext) -> list[View]:
    g = graph.shared(ctx)
    out: list[View] = []
    for date, report in ctx.scan_dailies(flags.GLOBE_DOMAIN):
        seen: set[str] = set()
        for i, t in dailies.sections(report):
            tid = str(t.get("theater_id") or "")
            devs = dailies.objs(t.get("developments"))
            if not tid or tid in seen or not devs:
                continue
            seen.add(tid)                                                           # the page addresses the first section of a theater in a report
            ref = g["refs"].get(tid) or {"id": tid, "name": str(t["name"]), "direction": "unclear", "band": "unassessed", "linked": False}
            body = {"date": date, "theater": ref, "name": t["name"], "anchor": dailies.anchor(tid, i), "index": i,
                    "developments": devs[: flags.EVENT_DEVELOPMENTS],
                    "actor_isos": [[mentions.iso_of(a) for a in dailies.strs(d.get("actors"))] for d in devs[: flags.EVENT_DEVELOPMENTS]],
                    "domain": str(report.get("domain") or flags.GLOBE_DOMAIN)}
            out.append(make("event", f"event/{date}/{tid}", body, as_of=date, sources=[("dailies", f"daily/{flags.GLOBE_DOMAIN}/{date}.json")]))
    return out
