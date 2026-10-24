"""
``views/hud.json``: the /globe page. Two blocks, both moved from the site's per-request builders (``lib/globe-data.ts``, ``lib/globe-hud.ts``) to the server:

    globe   ``GlobeData`` (lib/globe/data.ts): per-country channel rows (newest mention, dominant theme, direction, theaters tied) and the day's theater dots
    hud     ``HudData`` without its live block: today's report as theme-dotted lines, theaters with their Pulses, the Pulses that moved most, the calendar
            and sanctions rows the panels show (raw rows; the site words them), the paper trader

The live counters and anomaly flags stay a live read on the site (they change every few minutes; a view is rebuilt every half hour at most).
Everything uses the same ``mentions.daily_mentions`` walker as the country panel's brief history, so a dot and a colour can never disagree.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from . import dailies, flags, graph, mentions, themes
from .base import View, make
from .context import ViewContext

DIR_ORDER = ("rising", "steady", "easing", "unclear")
SANCTION_RECENT_DAYS = 21
GLOBE_SANCTION_DAYS = 30
GLOBE_CALENDAR_DAYS = 30


def _centre(t: dict[str, Any]) -> dict[str, float] | None:
    box = (t.get("map") or {}).get("bbox") if isinstance(t.get("map"), dict) else None
    if isinstance(box, list) and len(box) == 4 and all(isinstance(x, (int, float)) for x in box):
        return {"lon": (box[0] + box[2]) / 2, "lat": (box[1] + box[3]) / 2}
    pts = [p for d in dailies.objs(t.get("developments")) if isinstance((p := d.get("place")), dict) and isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float))]
    if not pts:
        return None
    return {"lon": sum(p["lon"] for p in pts) / len(pts), "lat": sum(p["lat"] for p in pts) / len(pts)}


def globe(ctx: ViewContext, g: dict[str, Any]) -> dict[str, Any] | None:
    dates = ctx.daily_dates(flags.GLOBE_DOMAIN)
    reports = [(d, r) for d in dates[: flags.GLOBE_DAILIES] if (r := ctx.daily(flags.GLOBE_DOMAIN, d))]
    if not reports:
        return None
    now_ms = ctx.now.timestamp() * 1000
    newest: dict[str, int] = {}
    tally: dict[str, dict[str, float]] = defaultdict(dict)
    headline: dict[str, dict[str, str]] = {}

    def see(iso: str, theme: str, base: float, t_ms: float | None) -> None:
        if t_ms is not None:
            newest[iso] = max(newest.get(iso, 0), round(min(t_ms, now_ms) / 1000))
        age = 0.0 if t_ms is None else (now_ms - t_ms) / 86_400_000
        tally[iso][theme] = tally[iso].get(theme, 0.0) + base * themes.decay(age)

    for d, report in reports:                                                          # newest first, so the first headline seen for a state is its newest
        for m in mentions.daily_mentions(report, d, dates):
            for iso in m.isos:
                see(iso, m.theme, m.base, m.t_ms)
                if m.text and iso not in headline:
                    headline[iso] = {"text": m.text, "date": m.date, "href": m.href}
    since = (ctx.now.date() - timedelta(days=GLOBE_SANCTION_DAYS)).isoformat()
    for s in ctx.rows("sanctions/recent.json", "rows"):
        if str(s.get("on_date")) >= since:
            for iso in dailies.strs(s.get("countries")):
                see(iso.upper(), "economy", 1.0, themes.ms(f"{s['on_date']}T12:00:00Z"))
    for c in ctx.rows("calendar/next.json", "items"):
        if c.get("active") is not False and ctx.today <= str(c.get("end_date") or c.get("on_date")) and str(c.get("on_date")) <= (ctx.now.date() + timedelta(days=GLOBE_CALENDAR_DAYS)).isoformat():
            theme = "economy" if c.get("kind") == "central_bank" else "energy" if c.get("kind") == "opec" else "politics"
            for iso in dailies.strs(c.get("countries")):
                see(iso.upper(), theme, 0.5, None)                                      # ahead, not new: it tints the theme but never the recency
    hot: dict[str, int] = defaultdict(int)
    for a in ctx.rows("live/anomalies.json", "anomalies"):
        if not a.get("active"):
            continue
        series = str(a.get("series") or "")
        theme = "energy" if series.startswith("ship.tanker") else "conflict" if series.startswith("air.military") else "disaster" if a.get("layer") == "fire" else "economy"
        t_ms = themes.ms(str(a.get("last_seen") or a.get("starts_at") or ""))
        for iso in dailies.strs(a.get("countries")):
            if len(iso) == 2:
                hot[iso] += 1
                see(iso, theme, 1.0, t_ms if t_ms is not None else now_ms)

    refs, ties, names = g["refs"], g["ties"], g["names"]
    by_country: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for theater, m in ties.items():
        if theater in refs:
            for iso, w in m.items():
                by_country[iso].append((theater, w))
    countries: dict[str, Any] = {}
    for iso in sorted(set(by_country) | set(newest) | set(hot)):
        tied = sorted(by_country.get(iso, []), key=lambda x: -x[1])
        rows = [{"id": refs[t]["id"], "name": refs[t]["name"], "dir": refs[t]["direction"], "href": f"/situations/{t}" if refs[t]["linked"] else ""} for t, _ in tied]
        dirs = {r["dir"] for r in rows}
        countries[iso] = {"n": len(rows), "dir": next((d for d in DIR_ORDER if d in dirs), None), "t": newest.get(iso), "th": themes.dominant(tally.get(iso, {})), "hot": hot.get(iso, 0),
                          "name": names.get(iso) or "", "theaters": rows, "headline": headline.get(iso), "page": iso in names or bool(rows)}
    top_date, top = reports[0]
    dots = []
    for i, t in dailies.sections(top):
        c = _centre(t)
        tid = str(t.get("theater_id") or "")
        iso = [i2 for i2, _ in sorted(ties.get(tid, {}).items(), key=lambda kv: -kv[1])[: flags.HUD_TIES_PER_THEATER]]
        esc = t.get("escalation") if isinstance(t.get("escalation"), dict) else {}
        temp = t.get("temperature") if isinstance(t.get("temperature"), dict) else {}
        dots.append({"id": tid, "name": t["name"], "dir": esc.get("direction") or "unclear", "heat": temp.get("heat") or 0, "lon": c["lon"] if c else None,
                     "lat": c["lat"] if c else None, "iso": iso, "href": f"{dailies.day_href(mentions.BASE, top_date, dates)}#{dailies.anchor(tid or str(t['name']), i)}", "date": top_date})
    return {"asOf": top_date, "countries": countries, "theaters": dots}


def _hud_pulse(p: dict[str, Any]) -> dict[str, Any]:
    return {"id": p.get("id"), "title": p.get("title") or p.get("name"), "band": p.get("band") or "unassessed", "position": p.get("position"), "change7d": p.get("velocity_7d"),
            "history": [h.get("position") for h in dailies.objs(p.get("history"))][-flags.HUD_HISTORY_POINTS:],
            "iso": [c for c in dailies.strs(p.get("actors_iso2")) if len(c) == 2], "href": f"/pulses#pulse-{p.get('id')}"}


def hud(ctx: ViewContext, g: dict[str, Any]) -> dict[str, Any]:
    dates = ctx.daily_dates(flags.GLOBE_DOMAIN)
    top = ctx.daily(flags.GLOBE_DOMAIN, dates[0]) if dates else None
    snap = ctx.snapshot() or {}
    pulses = [p for s in dailies.objs(snap.get("situations")) for p in dailies.objs(s.get("pulses")) if p.get("position") is not None and len(dailies.objs(p.get("history"))) >= 2]
    by_id = {p["id"]: _hud_pulse(p) for p in pulses}
    movers = [_hud_pulse(p) for p in sorted(pulses, key=lambda p: -abs(p.get("velocity_7d") or 0))[: flags.HUD_PULSES]]
    block = theaters = None
    if top:
        d = top["date"] if top.get("date") else dates[0]
        ms_ = mentions.daily_mentions(top, d, dates)
        pick = ([m for m in ms_ if m.kind == "section"] + [m for m in ms_ if m.kind == "development"])[: flags.HUD_DAILY_ITEMS]
        block = {"date": d, "headline": dailies.headline(top),
                 "items": [{"theme": m.theme, "text": m.text, "href": m.href, "date": m.date, "kind": m.kind, "iso": list(m.isos)} for m in pick]}
        theaters = []
        for i, t in dailies.sections(top):
            tid = str(t.get("theater_id") or "")
            temp = t.get("temperature") if isinstance(t.get("temperature"), dict) else {}
            esc = t.get("escalation") if isinstance(t.get("escalation"), dict) else {}
            theaters.append({
                "id": tid, "name": t["name"], "heat": temp.get("heat") or 0, "trend": temp.get("trend") or "steady", "dir": esc.get("direction") or "unclear",
                "pace": esc.get("pace") or "flat", "line": dailies.lead(t, 300), "href": f"{dailies.day_href(mentions.BASE, d, dates)}#{dailies.anchor(tid or str(t['name']), i)}",
                "iso": [iso for iso, _ in sorted(g["ties"].get(tid, {}).items(), key=lambda kv: -kv[1])[: flags.HUD_TIES_PER_THEATER]],
                "pulses": [by_id.get(p.get("id")) or {"id": p.get("id"), "title": p.get("title") or p.get("name"), "band": p.get("band") or "unassessed", "position": p.get("position"),
                                                      "change7d": p.get("change_7d"), "history": [], "iso": dailies.strs(p.get("actors_iso2")), "href": f"/pulses#pulse-{p.get('id')}"}
                           for p in dailies.objs(t.get("pulses"))]})
        theaters.sort(key=lambda x: -(x["heat"] or 0))
    today = date.fromisoformat(ctx.today)
    ahead_to = (today + timedelta(days=flags.HUD_COMING_DAYS)).isoformat()
    coming = sorted((c for c in ctx.rows("calendar/next.json", "items") if c.get("active") is not False and int(c.get("importance") or 2) >= 2 and ctx.today <= str(c.get("end_date") or c.get("on_date")) and str(c.get("on_date")) <= ahead_to),
                    key=lambda c: (str(c.get("on_date")), -int(c.get("importance") or 2), str(c.get("title"))))[: flags.HUD_COMING]
    since = (today - timedelta(days=SANCTION_RECENT_DAYS)).isoformat()
    sanctions = sorted((r for r in ctx.rows("sanctions/recent.json", "rows") if r.get("action") == "designated" and str(r.get("on_date")) >= since),
                       key=lambda r: str(r.get("on_date")), reverse=True)[: flags.HUD_SANCTIONS]
    return {"asOf": dates[0] if dates else "", "daily": block, "theaters": theaters or [], "pulses": movers, "coming": coming, "sanctions": sanctions, "trader": trader(ctx)}


def trader(ctx: ViewContext) -> dict[str, Any] | None:
    rec = ctx.table("data/track-record.json")
    t = rec.get("trader") if isinstance(rec, dict) else None
    if not isinstance(t, dict):
        return None
    curve = [{"day": c.get("day"), "flat": c.get("flat"), "trader": c.get("trader")} for c in dailies.objs(t.get("curve")) if c.get("trader") is not None][-flags.HUD_CURVE_DAYS:]
    if not curve:
        return None
    summary, limits = t.get("summary") or {}, t.get("limits") or {}
    positions = sorted(dailies.objs(t.get("open_positions")), key=lambda p: -abs(p.get("pnl") or 0))[: flags.HUD_POSITIONS]
    return {"asOf": rec.get("as_of", ""), "bankroll": limits.get("bankroll"), "equity": summary.get("equity"), "pnl": summary.get("pnl"), "open": summary.get("open"), "curve": curve,
            "positions": [{k: p.get(k) for k in ("question", "side", "pnl", "value", "url")} for p in positions]}


def build(ctx: ViewContext) -> list[View]:
    g = graph.shared(ctx)
    body = {"globe": globe(ctx, g), "hud": hud(ctx, g)}
    return [make("hud", "hud", body, as_of=str((body["globe"] or {}).get("asOf") or body["hud"]["asOf"]),
                 sources=[("dailies", "daily/geopolitics"), ("actors", "actors/*.json"), ("sanctions", "sanctions/recent.json"), ("calendar", "calendar/next.json"),
                          ("pulses", "snapshots/latest"), ("markets", "data/track-record.json"), ("live", "live/anomalies.json")])]
