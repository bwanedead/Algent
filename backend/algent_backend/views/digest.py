"""
A digest of a persisted daily: the same document shape, with only what an overview needs left in it (the sections' names, headlines, pulses, trackers and
visual stills; no maps, developments, statements, context or outlook). The site parses it with the parser it uses for the full report, so Home and the Daily
hub render from a few KB instead of a 100-800 KB document and need no second reader.
"""

from __future__ import annotations

from typing import Any

from . import dailies

_PULSE = ("id", "name", "title", "actors_iso2", "position", "band", "change_24h", "change_7d")
_VISUAL = ("id", "kind", "title", "caption", "asset", "schematic", "scene", "spec", "preview", "as_of", "ai_label", "sources")
_TRACKER_DROP = ("reasons", "outside_note")             # prose the overview never prints; every other tracker field is kept (movers draw a sparkline from `spark`)
BOTTOM_LINE = 600


def _theater(t: dict[str, Any]) -> dict[str, Any]:
    nums = t.get("numbers") if isinstance(t.get("numbers"), dict) else {}
    out: dict[str, Any] = {k: t.get(k) for k in ("theater_id", "name", "kind", "spotlight", "edition", "temperature", "escalation", "headline", "brief_slug") if k in t}
    out["bottom_line"] = dailies.clip(t.get("bottom_line"), BOTTOM_LINE)
    out["pulses"] = [{k: p.get(k) for k in _PULSE if k in p} for p in dailies.objs(t.get("pulses"))]
    out["visuals"] = [{k: v.get(k) for k in _VISUAL if k in v} for v in dailies.objs(t.get("visuals"))]
    out["updates"] = [{"theater_id": u.get("theater_id"), "name": u.get("name"), "kind": "update", "edition": u.get("edition")} for u in dailies.objs(t.get("updates"))]
    trackers = [{k: v for k, v in tr.items() if k not in _TRACKER_DROP} for tr in dailies.objs(nums.get("trackers"))]
    if trackers:
        out["numbers"] = {"as_of": nums.get("as_of", ""), "trackers": trackers, "actors": []}
    return out


def digest(report: dict[str, Any]) -> dict[str, Any]:
    """The overview form of one daily (``ohmega.daily/1``)."""
    return {"schema": report.get("schema", "ohmega.daily/1"), "domain": report.get("domain", ""), "date": report.get("date", ""), "built_at": report.get("built_at", ""),
            "researched": report.get("researched") is True,
            "editions": [{k: e.get(k) for k in ("n", "label", "cycle", "built_at")} for e in dailies.objs(report.get("editions"))],
            "summary": {"headline": dailies.headline(report), "the_day": dailies.the_day(report)},
            "theaters": [_theater(t) for t in dailies.objs(report.get("theaters"))]}
