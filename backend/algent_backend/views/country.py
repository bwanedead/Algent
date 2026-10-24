"""
``views/country/<ISO2>.json``: everything the site and an agent need to know about one state, built once on the server.

It replaces, per request, the globe panel's walk over up to 30 dailies plus every actor page (for the medians), and the actor page's entity index,
sanctions, calendar, grid and snapshot reads. One country, one small file:

    panel       the globe panel exactly as ``CountryPanel`` (lib/globe/data.ts): stat bars against the profiled median, counts, grid line, leaders and the
                brief history (the newest ``COUNTRY_BRIEFS``, each with the theme the map fill used). Stats carry raw values and units; the site formats them.
    profile     name, region, capital, leaders (the actor page itself still reads ``actors/<ISO>.json`` for the figures)
    context     the actor page's links: theaters it is tied to, what its officials said, recent developments, related states
    sanctions / calendar / grid   the country's rows (raw, as their products publish them; the site filters "still ahead" at render)
    snapshot    the Pulses its actor page lists, as a snapshot holding only those
    relations / series / about   from the corpus index when one exists: top typed relations, key series (with basis), how much the record says about it
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from algent_backend.actors import registry

from . import dailies, flags, graph, mentions, situation
from .base import View, make
from .context import ISO, ViewContext

#: Stat bars of the globe panel (ids are the actor profile's field ids): the same list lib/globe-country.ts carried.
STATS = (("population", "Population"), ("gdp", "GDP"), ("gdp_pc", "GDP per person"), ("milex", "Military spending"), ("milex_pct", "Military, share of GDP"),
         ("energy_import_pct", "Net energy imports, share of use"), ("fuel_exports_pct", "Fuels, share of exports"), ("gov_debt", "Government debt, share of GDP"),
         ("reserves_usd", "Foreign reserves"))
MIN_FOR_MEDIAN = 5
SANCTIONS_WINDOW_DAYS = 90         # lib/sanctions-shared.ts: the globe panel counts the last 90 days
CALENDAR_PANEL_DAYS = 45
CALENDAR_PAGE_DAYS = 120
DAILIES_FOR_DEVELOPMENTS = 3
BRIEF_DAILIES = 30                 # the newest reports the brief history reads (what the panel read before)


def field_of(actor: dict[str, Any], fid: str) -> dict[str, Any] | None:
    groups = actor.get("groups") if isinstance(actor.get("groups"), dict) else {}
    for rows in groups.values():
        for f in dailies.objs(rows):
            if f.get("id") == fid and isinstance(f.get("value"), (int, float)):
                return f
    return None


def medians(ctx: ViewContext) -> tuple[dict[str, float], int]:
    def compute() -> tuple[dict[str, float], int]:
        actors = [a for a in (ctx.actor(i) for i in ctx.actor_isos()) if a]
        out: dict[str, float] = {}
        for fid, _ in STATS:
            vals = [f["value"] for a in actors if (f := field_of(a, fid)) and f["value"] > 0]
            if len(vals) >= MIN_FOR_MEDIAN:
                out[fid] = float(statistics.median(vals))
        return out, len(actors)
    return ctx.memo("medians", compute)


def _pos(v: float, med: float | None) -> float | None:
    return min(1.0, max(0.0, 0.5 + 0.5 * math.log10(v / med))) if med and v > 0 else None


def stats_of(actor: dict[str, Any] | None, med: dict[str, float]) -> list[dict[str, Any]]:
    out = []
    for fid, label in STATS:
        f = field_of(actor, fid) if actor else None
        if f:
            out.append({"id": fid, "label": label, "value": f["value"], "unit": f.get("unit") or "number", "year": f.get("year"),
                        "pos": _pos(f["value"], med.get(fid)), "median": med.get(fid)})
    return out


def briefs_by_country(ctx: ViewContext) -> dict[str, list[dict[str, Any]]]:
    """Every section and development of the newest geopolitics dailies, bucketed by the countries it names, newest first (one line per text per day)."""
    def compute() -> dict[str, list[dict[str, Any]]]:
        dates = ctx.daily_dates(flags.GLOBE_DOMAIN)
        out: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for d in dates[:BRIEF_DAILIES]:
            report = ctx.daily(flags.GLOBE_DOMAIN, d)
            if not report:
                continue
            seen: set[tuple[str, str]] = set()
            for m in mentions.daily_mentions(report, d, dates):
                if not m.text:
                    continue
                for iso in m.isos:
                    if (iso, m.text) not in seen:
                        seen.add((iso, m.text))
                        out[iso].append({"theme": m.theme, "date": m.date, "text": m.text, "href": m.href, "kind": m.kind})
        return out
    return ctx.memo("briefs_by_country", compute)


def _recent(rows: list[dict[str, Any]], key: str, since: str) -> list[dict[str, Any]]:
    return [r for r in rows if str(r.get(key) or "") >= since]


def sanctions_of(ctx: ViewContext, iso: str) -> tuple[list[dict[str, Any]], int]:
    doc = ctx.table(f"sanctions/country/{iso}.json")
    rows = [r for r in dailies.objs(doc.get("rows")) if r.get("action") in ("designated", "delisted")] if isinstance(doc, dict) else []
    rows.sort(key=lambda r: (str(r.get("on_date")), str(r.get("observed_on"))), reverse=True)
    return rows[: flags.COUNTRY_SANCTIONS], len(rows)


def calendar_of(ctx: ViewContext, iso: str) -> list[dict[str, Any]]:
    """Active items naming the country from a week back to ``CALENDAR_PAGE_DAYS`` ahead, soonest first (the site keeps what is still ahead at render)."""
    t = date.fromisoformat(ctx.today)
    lo, hi = (t - timedelta(days=7)).isoformat(), (t + timedelta(days=CALENDAR_PAGE_DAYS)).isoformat()
    rows = [r for r in ctx.rows("calendar/next.json", "items") if r.get("active") is not False and int(r.get("importance") or 2) >= 2 and iso in (r.get("countries") or []) and lo <= str(r.get("on_date")) <= hi]
    rows.sort(key=lambda r: (str(r.get("on_date")), str(r.get("kind")), str(r.get("title"))))
    return rows[: flags.COUNTRY_CALENDAR]


def pulses_of(ctx: ViewContext, actor: dict[str, Any] | None) -> dict[str, Any] | None:
    """The Pulses an actor page lists (its ``involved.pulses`` ids) as a snapshot holding only those, so the site parses them with the snapshot parser."""
    ids = {str(p.get("id")) for p in dailies.objs(((actor or {}).get("involved") or {}).get("pulses"))}
    return situation.mini_snapshot(ctx, ids, set()) if ids else None


def developments_of(ctx: ViewContext, iso: str) -> list[dict[str, Any]]:
    dates = ctx.daily_dates(flags.GLOBE_DOMAIN)[:DAILIES_FOR_DEVELOPMENTS]
    out: list[dict[str, Any]] = []
    for d in dates:
        report = ctx.daily(flags.GLOBE_DOMAIN, d)
        if not report:
            continue
        secs = dailies.sections(report)
        for i, t in secs:
            tid = str(t.get("theater_id") or t.get("name"))
            unique = sum(1 for _, o in secs if (o.get("theater_id") or o.get("name")) == tid) == 1
            for n, dev in enumerate(dailies.objs(t.get("developments"))):
                place = dev.get("place") if isinstance(dev.get("place"), dict) else {}
                named = any(mentions.iso_of(a) == iso for a in dailies.strs(dev.get("actors"))) or (place.get("country") and mentions.iso_of(str(place["country"])) == iso)
                if named:
                    out.append({"date": d, "theater": str(t["name"]), "theaterId": tid, "headline": str(dev.get("headline") or ""),
                                "detail": dailies.clip(dev.get("detail"), 300), "when": str(dev.get("when") or ""), "href": f"/daily/geopolitics/{d}#{dailies.anchor(tid, i)}",
                                "event": f"/intel/events/{d}/{tid}/{n + 1}" if unique else ""})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out[: flags.COUNTRY_DEVELOPMENTS]


def context_of(ctx: ViewContext, iso: str, g: dict[str, Any]) -> dict[str, Any]:
    refs, ties, names = g["refs"], g["ties"], g["names"]
    name = lambda code: names.get(code) or registry.display_name(code, code)                  # noqa: E731
    mine = {t: m[iso] for t, m in ties.items() if iso in m}
    rank = {"rising": 0, "steady": 1, "unclear": 2, "easing": 3}
    theaters = sorted(({**refs.get(t, {"id": t, "name": t, "direction": "unclear", "band": "unassessed", "linked": False}), "mentions": w} for t, w in mine.items()),
                      key=lambda x: (rank.get(x["direction"], 2), -x["mentions"], x["name"]))
    record = ctx.record() or {}
    rows = dailies.objs(record.get("statements"))
    said = [r for r in rows if r.get("iso2") == iso][: flags.COUNTRY_SAID]
    about = sum(1 for r in rows if iso in (r.get("about_iso2") or []))
    rel: dict[str, list[dict[str, str]]] = defaultdict(list)
    for t in theaters:
        for other in ties.get(t["id"], {}):
            if other != iso:
                rel[other].append({"id": t["id"], "name": t["name"]})
    related = sorted(({"iso2": c, "name": name(c), "via": via} for c, via in rel.items()), key=lambda r: (-len(r["via"]), r["name"]))[: flags.COUNTRY_RELATED]
    return {"theaters": theaters, "said": said, "saidAbout": about, "developments": developments_of(ctx, iso), "related": related}


def corpus_block(ctx: ViewContext, iso: str) -> dict[str, Any]:
    """Typed relations, key series (with basis) and how much the record holds, from the corpus index; empty when none was built."""
    if ctx.corpus is None:
        return {}
    ent = f"country:{iso}"
    try:
        c = ctx.corpus
        edges = c.entity(ent) or {}
        series = [{**{k: s[k] for k in ("metric", "label", "unit", "basis", "n", "first", "last")}, "points": [[ts, v] for ts, v in s.get("points", [])[-flags.SERIES_POINTS:]]}
                  for s in c.series(ent, points=True, limit=flags.SERIES_PER_ENTITY)]
        return {"relations": edges.get("relations", [])[:flags.ENTITY_RELATED], "series": series, "about": edges.get("counts", {})}
    except Exception as exc:  # noqa: BLE001 - the corpus is an addition; the staged documents carry the view alone
        print(f"[views] country {iso}: corpus block skipped: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        return {}


def isos(ctx: ViewContext, g: dict[str, Any], briefs: dict[str, list]) -> list[str]:
    """Countries with something to show: a profile, a tie to a theater, a brief naming it, a sanction, a calendar item or a grid rollup."""
    found = set(ctx.actor_isos()) | set(g["names"]) | {c for m in g["ties"].values() for c in m} | set(briefs)
    for r in (x for x in ctx.rows("calendar/next.json", "items") if int(x.get("importance") or 2) >= 2):
        found |= {c for c in r.get("countries") or [] if isinstance(c, str)}
    return sorted(c for c in found if ISO.match(c) and registry.get(c))


def build_one(ctx: ViewContext, iso: str, g: dict[str, Any], briefs: dict[str, list[dict[str, Any]]]) -> View:
    actor = ctx.actor(iso)
    med, profiled = medians(ctx)
    country = registry.get(iso)
    name = (actor or {}).get("name") or (country.name if country else iso)
    sanctions, sanctions_total = sanctions_of(ctx, iso)
    calendar = calendar_of(ctx, iso)
    grid = ctx.table(f"geo/grid/{iso}.json")
    grid = grid if isinstance(grid, dict) and grid.get("windows") else None
    anomalies = [a for a in ctx.rows("live/anomalies.json", "anomalies") if a.get("active") and iso in (a.get("countries") or [])]
    my_briefs = briefs.get(iso, [])
    lead = (actor or {}).get("leadership") if isinstance((actor or {}).get("leadership"), dict) else {}
    leaders = {"head_of_state": ((lead or {}).get("head_of_state") or {}).get("name", ""), "head_of_government": ((lead or {}).get("head_of_government") or {}).get("name", "")}
    context = context_of(ctx, iso, g)
    today = date.fromisoformat(ctx.today)
    week_ago = (today - timedelta(days=7)).isoformat()
    panel = {
        "iso": iso, "stats": stats_of(actor, med), "profiled": profiled,
        "counts": {"theaters": len(dailies.objs(((actor or {}).get("involved") or {}).get("theaters"))) if actor else 0,
                   "statements7d": sum(1 for s in dailies.objs((actor or {}).get("statements")) if str(s.get("date")) >= week_ago),
                   "sanctions": sum(1 for r in sanctions if str(r.get("on_date")) >= (today - timedelta(days=SANCTIONS_WINDOW_DAYS)).isoformat()),
                   "calendar": sum(1 for r in calendar if str(r.get("end_date") or r.get("on_date")) >= ctx.today and str(r.get("on_date")) <= (today + timedelta(days=CALENDAR_PANEL_DAYS)).isoformat()),
                   "anomalies": len(anomalies)},
        "grid": {"line": grid.get("line", ""), "asOf": grid.get("as_of", "")} if grid and grid.get("line") else None,
        "leaders": leaders, "briefs": my_briefs[: flags.COUNTRY_BRIEFS], "briefsTotal": len(my_briefs),
    }
    body = {
        "iso": iso, "name": name, "region": (actor or {}).get("region") or (country.region if country else ""), "capital": (actor or {}).get("capital") or (country.capital if country else ""),
        "profiled": actor is not None, "panel": panel, "context": context, "sanctions": sanctions, "sanctionsTotal": sanctions_total, "calendar": calendar, "grid": grid,
        "snapshot": pulses_of(ctx, actor),
        "anomalies": [{k: a.get(k) for k in ("id", "sentence", "direction", "confidence", "series", "starts_at", "ends_at")} for a in anomalies[:10]],
        **corpus_block(ctx, iso),
    }
    return make("country", f"country/{iso}", body, as_of=(ctx.daily_dates(flags.GLOBE_DOMAIN) or [""])[0],
                sources=[("actors", f"actors/{iso}.json"), ("dailies", "daily/geopolitics"), ("sanctions", f"sanctions/country/{iso}.json"), ("calendar", "calendar/next.json"),
                         ("geoledger", f"geo/grid/{iso}.json"), ("corpus_index", "country entity")])


def build(ctx: ViewContext) -> list[View]:
    g = graph.shared(ctx)
    briefs = briefs_by_country(ctx)
    return [build_one(ctx, iso, g, briefs) for iso in isos(ctx, g, briefs)]
