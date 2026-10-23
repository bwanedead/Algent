"""
``views/graph.json``: the small shared graph every entity link on the site is computed from - which theaters exist (and have a page), which states have a
page, and how strongly the sources tie each theater to each state. It replaces the site's per-request ``entityIndex`` (every actor page, the dossier
index and three dailies, loaded to answer "is there a page for this?" and "who is tied to what?").

Weights are the ones ``lib/entities.ts`` used: an actor page's own theater mention count (at least 1), plus one for each time a recent geopolitics
daily's Pulses or numbers name the state in that theater.
"""

from __future__ import annotations

from typing import Any

from . import dailies, flags
from .base import View, make
from .context import ISO, ViewContext

DAILIES_READ = 3                          # recent reports mined for ties (lib/entities.ts DAILIES_READ)
BAND_RANK = {"unassessed": 0, "calm": 1, "elevated": 2, "severe": 3, "critical": 4}


def max_band(pulses: list[dict[str, Any]]) -> str:
    best = "unassessed"
    for p in pulses:
        b = str(p.get("band") or "unassessed")
        if p.get("position") is not None and BAND_RANK.get(b, 0) > BAND_RANK[best]:
            best = b
    return best


def compute(ctx: ViewContext) -> dict[str, Any]:
    """``{"refs": {theater_id: ref}, "ties": {theater_id: {iso: weight}}, "names": {iso: name}}`` for the geopolitics desk (as the site read it)."""
    refs: dict[str, dict[str, Any]] = {}
    for r in ctx.dossier_index():
        if not r.get("merged_into"):
            refs[str(r["theater_id"])] = {"id": str(r["theater_id"]), "name": str(r.get("name") or r["theater_id"]),
                                          "direction": str(r.get("escalation_direction") or "unclear"), "band": str(r.get("max_band") or "unassessed"), "linked": True}
    dates = ctx.daily_dates(flags.GLOBE_DOMAIN)[:DAILIES_READ]
    reports = [r for r in (ctx.daily(flags.GLOBE_DOMAIN, d) for d in dates) if r]
    for report in reports:                                                    # a theater in a recent report but without a dossier is named, not linked
        for _, t in dailies.sections(report):
            tid = str(t.get("theater_id") or t.get("name"))
            if tid not in refs:
                esc = t.get("escalation") if isinstance(t.get("escalation"), dict) else {}
                refs[tid] = {"id": tid, "name": str(t["name"]), "direction": str(esc.get("direction") or "unclear"),
                             "band": max_band(dailies.objs(t.get("pulses"))), "linked": False}
    ties: dict[str, dict[str, float]] = {}
    names: dict[str, str] = {}

    def tie(theater: str, iso: str, w: float) -> None:
        if theater and ISO.match(iso):
            ties.setdefault(theater, {})
            ties[theater][iso] = ties[theater].get(iso, 0) + w

    for iso in ctx.actor_isos():
        a = ctx.actor(iso) or {}
        names[iso] = str(a.get("name") or iso)
        involved = a.get("involved") if isinstance(a.get("involved"), dict) else {}
        for t in dailies.objs(involved.get("theaters")):
            tie(str(t.get("id") or ""), iso, max(1, int(t.get("mentions") or 1)))
    for report in reports:
        for t in dailies.objs(report.get("theaters")):
            tid = str(t.get("theater_id") or "")
            for iso in dailies.pulse_isos(t):
                tie(tid, iso, 1)
            for iso in dailies.number_isos(t):
                tie(tid, iso, 1)
    return {"refs": refs, "ties": ties, "names": names}


def shared(ctx: ViewContext) -> dict[str, Any]:
    """The graph of this run, computed once for every builder that needs theater refs or ties."""
    return ctx.memo("graph", lambda: compute(ctx))


def build(ctx: ViewContext) -> list[View]:
    g = shared(ctx)
    weight = lambda tid: sum(g["ties"].get(tid, {}).values())      # noqa: E731
    keep = sorted(g["refs"], key=lambda t: (-weight(t), t))[: flags.GRAPH_REFS]
    linkable = sorted({iso for iso in g["names"]} | {iso for t in keep for iso in g["ties"].get(t, {})})
    as_of = (ctx.daily_dates(flags.GLOBE_DOMAIN) or [""])[0]
    body = {"theaters": [g["refs"][t] for t in sorted(keep)],
            "ties": {t: {iso: round(w, 2) for iso, w in sorted(g["ties"].get(t, {}).items())} for t in sorted(keep) if g["ties"].get(t)},
            "names": g["names"], "linkable": linkable}
    return [make("graph", "graph", body, as_of=as_of, sources=[("dossiers", "theaters/index.json"), ("actors", "actors/*.json"), ("dailies", "daily/geopolitics")])]
