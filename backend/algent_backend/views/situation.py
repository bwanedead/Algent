"""
``views/situation/<id>.json`` and ``views/situations.json``.

A situation page used to read every daily of every desk to find the days that covered it, and every actor page to find who it involves. The view
carries what the page needs besides its dossier (``theaters/<id>.json``, one document the page still reads whole):

    stream      ``days_total``, the newest ``STREAM_FULL_DAYS`` days as full Daily sections (raw, parsed by the site exactly as the Daily page parses
                them), and a compact index row for every other day (date, headline, direction, visuals, a link into that day's report)
    snapshot    a snapshot holding only the Pulses this page draws (the dossier's and its full sections')
    involved / states / related    the states the theater involves (with the headline figures the scale strip draws), every state tied to it, and the theaters
                that share states with it
    pulses / actors / map_points / briefs    the same facts in agent-readable form

``situations.json`` is the index page and Home's "moving" list: one slim row per situation, grouped by desk.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from . import dailies, flags, graph, signals
from .base import View, make
from .context import ViewContext

_RANK = {"rising": 0, "easing": 1, "steady": 2, "unclear": 3}
STRIP_DAYS = 21                    # the situations index draws the last 21 days on one shared axis (components/situations/DeskPanel.tsx DAYS)


def edition_tag(report: dict[str, Any], n: int) -> str:
    """The "Added 17:30 UTC · Americas" tag of a section written by a later part (``editionTag`` in lib/daily.ts); '' for part 1."""
    e = next((x for x in dailies.objs(report.get("editions")) if x.get("n") == n), None)
    if n <= 1 or not e:
        return ""
    try:
        at = datetime.fromisoformat(str(e.get("built_at")).replace("Z", "+00:00")).astimezone(UTC).strftime("%H:%M UTC")
    except ValueError:
        at = ""
    tail = e.get("cycle") or e.get("label")
    return f"{f'Added {at}' if at else 'Added'}{f' · {tail}' if tail else ''}"


def _visual_rows(t: dict[str, Any]) -> list[dict[str, str]]:
    return [{"id": str(v.get("id") or ""), "kind": str(v.get("kind") or ""), "title": str(v.get("title") or "")} for v in dailies.objs(t.get("visuals"))]


def streams(ctx: ViewContext, keep_sections: int) -> dict[str, list[dict[str, Any]]]:
    """``{theater id: [day entries, newest first]}`` over every desk's whole archive, one daily in memory at a time. Each desk's newest ``keep_sections``
    entries of a theater keep their raw ``section`` (the page may show them in full); the rest are index rows only."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for desk in flags.DESKS:
        domain = str(desk["id"])
        dates = ctx.daily_dates(domain)
        kept: dict[str, int] = defaultdict(int)
        for date, report in ctx.scan_dailies(domain):                                          # newest first
            secs = dailies.sections(report)
            for i, t in secs:
                tid = str(t.get("theater_id") or "")
                if not tid:
                    continue
                anchor = dailies.anchor(tid, i)
                esc = t.get("escalation") if isinstance(t.get("escalation"), dict) else {}
                entry: dict[str, Any] = {
                    "date": date, "desk": domain, "anchor": anchor, "index": i, "headline": dailies.lead(t), "direction": str(esc.get("direction") or "unclear"),
                    "pace": str(esc.get("pace") or "flat"), "visuals": _visual_rows(t), "developments": len(dailies.objs(t.get("developments"))),
                    "updates": len(dailies.objs(t.get("updates"))), "href": f"{dailies.day_href(f'/daily/{domain}', date, dates)}#{anchor}",
                    "edition": edition_tag(report, int(t.get("edition") or 1)), "events": sum(1 for _, o in secs if o.get("theater_id") == tid) == 1,
                    "update_tags": [edition_tag(report, int(u.get("edition") or 1)) for u in dailies.objs(t.get("updates"))]}
                if kept[tid] < keep_sections:
                    kept[tid] += 1
                    entry["section"] = t
                out[tid].append(entry)
    return {tid: sorted(rows, key=lambda e: (e["date"], e["desk"]), reverse=True) for tid, rows in out.items()}


def _band_rank(b: str) -> int:
    return graph.BAND_RANK.get(b, 0)


def mini_snapshot(ctx: ViewContext, pulse_ids: set[str], names: set[str]) -> dict[str, Any] | None:
    snap = ctx.snapshot()
    if not snap:
        return None
    sits = []
    for s in dailies.objs(snap.get("situations")):
        keep = [p for p in dailies.objs(s.get("pulses")) if p.get("id") in pulse_ids or p.get("name") in names]
        if keep:
            sits.append({k: s.get(k) for k in ("id", "title", "summary", "domain")} | {"pulses": keep, "watches": []})
    return {"slug": snap.get("slug", ""), "built_at": snap.get("built_at", ""), "situations": sits, "theaters": [], "daily": [], "briefs": [], "forecasts": {}}


def _actor_lite(a: dict[str, Any]) -> dict[str, Any]:
    return {"iso2": a.get("iso2"), "name": a.get("name"), "headline": [{k: f.get(k) for k in ("id", "label", "unit", "value", "year", "rank", "of", "percentile")} for f in dailies.objs(a.get("headline"))]}


def build_one(ctx: ViewContext, tid: str, d: dict[str, Any], days: list[dict[str, Any]], g: dict[str, Any], full_days: int) -> View:
    refs, ties, names = g["refs"], g["ties"], g["names"]
    mine = ties.get(tid, {})
    involved = []
    for iso in ctx.actor_isos():
        a = ctx.actor(iso) or {}
        n = next((int(t.get("mentions") or 0) for t in dailies.objs((a.get("involved") or {}).get("theaters")) if t.get("id") == tid), 0)
        if n > 0:
            involved.append((n, str(a.get("name")), _actor_lite(a)))
    involved.sort(key=lambda x: (-x[0], x[1]))
    states = [{"iso2": iso, "name": names.get(iso, iso)} for iso, _ in sorted(mine.items(), key=lambda kv: (-kv[1], names.get(kv[0], kv[0])))][:40]
    related = []
    for other, m in ties.items():
        ref = refs.get(other)
        shared = [iso for iso in m if iso in mine]
        if other != tid and ref and ref["linked"] and shared:
            related.append({**ref, "shared": [{"iso2": iso, "name": names.get(iso, iso)} for iso in shared]})
    related.sort(key=lambda r: (-len(r["shared"]), _RANK.get(r["direction"], 3), r["name"]))
    top_states = [iso for iso, _ in sorted(mine.items(), key=lambda kv: (-kv[1], kv[0]))][:flags.SITUATION_STATES]
    signals_block = situation_signals(ctx, set(top_states))
    pulse_ids = {str(p.get("id")) for p in dailies.objs(d.get("pulses"))} | {str(p.get("id")) for e in days[:full_days] for p in dailies.objs(e.get("section", {}).get("pulses"))}
    pulse_names = {str(p.get("name")) for p in dailies.objs(d.get("pulses"))}
    newest_map = next((e["section"].get("map") for e in days[:full_days] if isinstance(e.get("section", {}).get("map"), dict)), None)
    points = [{k: p.get(k) for k in ("label", "date", "verification", "n", "lat", "lon")} for p in dailies.objs((newest_map or {}).get("points"))]
    body = {
        "id": tid, "name": d.get("name") or tid, "desk": dailies.desk_of_domain(str(d.get("domain") or "")), "domain": d.get("domain") or "",
        "stream": {"days_total": len(days), "full": days[:full_days], "index": [e for e in days[full_days:flags.STREAM_INDEX_DAYS]],
                   "index_total": max(0, len(days) - full_days)},
        "snapshot": mini_snapshot(ctx, pulse_ids, pulse_names),
        "involved": [x[2] for x in involved][:8], "states": states, "related": related[:12],
        "pulses": [{k: p.get(k) for k in ("id", "name", "position", "band", "situation")} | {"history": dailies.objs(p.get("history"))[-flags.HUD_HISTORY_POINTS:]}
                   for p in dailies.objs(d.get("pulses"))],
        "actors": dailies.objs(d.get("actors"))[:20], "map_points": points[:40], "places": dailies.objs(d.get("places"))[:20],
        "briefs": dailies.objs(d.get("briefs"))[:20], "current": d.get("current"), "signals": signals_block,
    }
    return make("situation", f"situation/{tid}", body, as_of=str(d.get("last_seen") or ""),
                sources=[("situations", f"theaters/{tid}.json"), ("dailies", "daily/*"), ("actors", "actors/*.json"), ("pulses", "snapshots/latest"), ("conflict", "conflict/country/*.json"), ("gnss", "gnss/latest.json")])


def situation_signals(ctx: ViewContext, isos: set[str]) -> dict[str, Any] | None:
    """What the measured layers show over the situation's main states: the strongest reported attacks of the last 30 days and the GPS-interference zones over them.
    Each is a count we make ourselves (a minimum) with its provenance; the block is None when neither product has anything for these states."""
    events: list[dict[str, Any]] = []
    total = 0
    for iso in sorted(isos):
        a = signals.attacks_of(ctx, iso, flags.SITUATION_ATTACKS)
        if a:
            total += a["total"]
            events += a["rows"]
    events.sort(key=lambda r: (r.get("coding") == "curated", r.get("fatalities") or 0, r.get("articles") or 0), reverse=True)
    jam = signals.gnss_in(ctx, isos, flags.COUNTRY_ZONES)
    if not events and not jam:
        return None
    return {"states": sorted(isos), "attacks": {"total": total, "window_days": 30, "rows": events[: flags.SITUATION_ATTACKS]} if events else None, "gnss": jam}


def fit(make_view: Any, steps: tuple[int, ...]) -> View:
    """Build with the most full days that fit the family's byte budget (a section can carry a whole map): the first step whose view is within budget."""
    view = None
    for k in steps:
        view = make_view(k)
        if not view.over_budget():
            if k < steps[0]:
                view.notes.append(f"stream trimmed to {k} full day(s) to fit the byte budget")
            return view
    assert view is not None
    return view


def build(ctx: ViewContext) -> list[View]:
    g = graph.shared(ctx)
    all_days = streams(ctx, flags.STREAM_FULL_DAYS)
    views = []
    for row in ctx.dossier_index():
        tid = str(row["theater_id"])
        d = ctx.dossier(tid)
        if d:
            views.append(fit(lambda k, tid=tid, d=d: build_one(ctx, tid, d, _days(all_days, tid, k), g, k), tuple(range(flags.STREAM_FULL_DAYS, -1, -1))))
    return views + build_index(ctx)


def _days(all_days: dict[str, list[dict[str, Any]]], tid: str, k: int) -> list[dict[str, Any]]:
    """The theater's day entries with only the newest ``k`` keeping their raw section."""
    return [({kk: v for kk, v in e.items() if kk != "section"} if i >= k else e) for i, e in enumerate(all_days.get(tid, []))]


# ── the index ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _quiet(row: dict[str, Any], now: datetime) -> bool:
    if row.get("state"):
        return row["state"] == "quiet"
    stamp = str(row.get("last_novel") or row.get("last_seen") or "")
    try:
        t = datetime.fromisoformat(stamp if "T" in stamp else f"{stamp}T00:00:00+00:00")
    except ValueError:
        return False
    return now - t.astimezone(UTC) > timedelta(days=flags.QUIET_AFTER_DAYS)


def _by_urgency(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Escalating first, then the most recently reported, then the longest-running, then by name (lib/situations.ts ``byUrgency``)."""
    out = sorted(rows, key=lambda r: str(r["item"].get("name") or ""))
    out.sort(key=lambda r: -int(r["item"].get("days_covered") or 0))
    out.sort(key=lambda r: str(r["item"].get("last_seen") or ""), reverse=True)
    out.sort(key=lambda r: _RANK.get(r["item"].get("escalation_direction"), 3))
    return out


def spotlight_one_off(row: dict[str, Any]) -> bool:
    return str(row.get("theater_id", "")).startswith("thr_spot_") and int(row.get("days_covered") or 0) <= 1


def build_index(ctx: ViewContext) -> list[View]:
    rows = []
    for item in ctx.dossier_index():
        if spotlight_one_off(item):
            continue
        d = ctx.dossier(str(item["theater_id"]))
        if d is None:
            continue
        esc = sorted(dailies.objs(d.get("escalation_history")), key=lambda e: str(e.get("date")))[-STRIP_DAYS:]
        cov = sorted(dailies.objs(d.get("coverage_series")), key=lambda c: str(c.get("day")))[-STRIP_DAYS:]
        rows.append({"item": item, "dossier": {"escalation_history": esc, "coverage_series": cov}})
    desks = []
    for desk in flags.DESKS:
        mine = [r for r in rows if dailies.desk_of_domain(str(r["item"].get("domain") or "")) == desk["id"]]
        desks.append({"desk": desk["id"],
                      "active": _by_urgency([r for r in mine if not r["item"].get("merged_into") and not _quiet(r["item"], ctx.now)]),
                      "quiet": _by_urgency([r for r in mine if not r["item"].get("merged_into") and _quiet(r["item"], ctx.now)]),
                      "merged": [r for r in mine if r["item"].get("merged_into")]})
    as_of = max((str(r["item"].get("last_seen") or "") for r in rows), default="")
    return [make("situations", "situations", {"desks": desks}, as_of=as_of, sources=[("situations", "theaters/index.json")])]
