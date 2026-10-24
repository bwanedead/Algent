"""
``views/home.json``: the "today" block of the Home page and the counts its doors print, so Home reads one small file for everything that is not live.

    reports     each desk's newest report as a digest (the site parses it with the Daily parser)
    snapshot    a snapshot with only what Home draws from it: the day's theaters' coverage series and the one Pulse that moved most this week
    moving      the situations escalating now, per desk, with their last report
    coming      calendar rows from a week back to two weeks ahead (the site keeps what is still ahead when it renders)
    facts       the numbers behind the doors (active situations, state profiles, statements on file, Pulses, calendar, sanctions)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import dailies, flags, situation
from .base import View, make
from .context import ViewContext
from .digest import digest

MOVING_PER_DESK = 2             # components/home/Today.tsx MOVING_PER_DESK
SPARK_DAYS = 14
SERIES_DAYS = 7                 # components/home/Hero.tsx SPARK_DAYS
SANCTIONS_WINDOW_DAYS = 90      # lib/sanctions-shared.ts SANCTIONS_WINDOW_DAYS
COMING_AHEAD_DAYS = 30


def mini_snapshot(ctx: ViewContext, report: dict[str, Any] | None) -> dict[str, Any] | None:
    snap = ctx.snapshot()
    if not snap:
        return None
    ids = {str(t.get("theater_id")) for _, t in dailies.sections(report or {})}
    names = {str(t.get("name")) for _, t in dailies.sections(report or {})}
    theaters = [{"id": t.get("id"), "name": t.get("name"), "series": dailies.objs(t.get("series"))[-SERIES_DAYS:]} for t in dailies.objs(snap.get("theaters"))
                if t.get("id") in ids or t.get("name") in names]
    moved = [(s, p) for s in dailies.objs(snap.get("situations")) for p in dailies.objs(s.get("pulses")) if p.get("position") is not None and p.get("velocity_7d") is not None]
    sits = []
    if moved:
        s, p = max(moved, key=lambda sp: abs(sp[1]["velocity_7d"]))
        sits = [{**{k: s.get(k) for k in ("id", "title", "summary", "domain")}, "pulses": [{**p, "history": dailies.objs(p.get("history"))[-SPARK_DAYS:]}], "watches": []}]
    return {"slug": snap.get("slug", ""), "built_at": snap.get("built_at", ""), "situations": sits, "theaters": theaters, "daily": [], "briefs": [], "forecasts": {}}


def facts(ctx: ViewContext, groups: list[dict[str, Any]], reports: dict[str, dict | None]) -> dict[str, Any]:
    active = [r for g in groups for r in g["active"]]
    snap = ctx.snapshot() or {}
    pulses = [p for s in dailies.objs(snap.get("situations")) for p in dailies.objs(s.get("pulses"))]
    record = ctx.record() or {}
    today = date.fromisoformat(ctx.today)
    horizon = (today + timedelta(days=COMING_AHEAD_DAYS)).isoformat()
    ahead = [r for r in ctx.rows("calendar/next.json", "items") if r.get("active") is not False and int(r.get("importance") or 2) >= 2 and today.isoformat() <= str(r.get("end_date") or r.get("on_date")) and str(r.get("on_date")) <= horizon]
    since = (today - timedelta(days=SANCTIONS_WINDOW_DAYS)).isoformat()
    sanctions = [r for r in ctx.rows("sanctions/recent.json", "rows") if str(r.get("on_date")) >= since]
    return {
        "daily_stamp": max((str(r.get("built_at") or r.get("date") or "") for r in reports.values() if r), default=""),
        "situations": {"active": len(active), "rising": sum(1 for r in active if r["item"].get("escalation_direction") == "rising"),
                       "stamp": max((str(r["item"].get("last_seen") or "") for r in active), default="")},
        "actors": len(ctx.actor_isos()),
        "record": {"count": record.get("count", 0), "shown": len(dailies.objs(record.get("statements"))), "total": record.get("total"), "window_days": record.get("window_days"),
                   "as_of": record.get("as_of", "")} if record else None,
        "pulses": {"total": len(pulses), "severe": sum(1 for p in pulses if p.get("band") in ("severe", "critical")), "built_at": snap.get("built_at", "")},
        "calendar_30d": len(ahead),
        "sanctions": {"additions": sum(1 for r in sanctions if r.get("action") == "designated"), "newest_observed": max((str(r.get("observed_on") or "") for r in sanctions), default="")},
    }


def build(ctx: ViewContext) -> list[View]:
    reports = {str(d["id"]): ctx.latest_daily(str(d["id"])) for d in flags.DESKS}
    index = situation.build_index(ctx)[0].body["desks"]
    moving = []
    for g in index:
        for r in [r for r in g["active"] if r["item"].get("escalation_direction") == "rising"][:MOVING_PER_DESK]:
            moving.append({"id": r["item"]["theater_id"], "name": r["item"].get("name"), "desk": g["desk"], "stamp": r["item"].get("last_seen", "")})
    today = date.fromisoformat(ctx.today)
    lo, hi = (today - timedelta(days=7)).isoformat(), (today + timedelta(days=14)).isoformat()
    coming = [r for r in ctx.rows("calendar/next.json", "items") if r.get("active") is not False and int(r.get("importance") or 2) >= 2 and lo <= str(r.get("on_date")) <= hi]   # routine items stay on /calendar
    body = {"reports": {k: digest(v) if v else None for k, v in reports.items()}, "snapshot": mini_snapshot(ctx, reports.get(flags.GLOBE_DOMAIN)), "moving": moving,
            "coming": coming, "facts": facts(ctx, index, reports)}
    as_of = max((str(r.get("date") or "") for r in reports.values() if r), default="")
    return [make("home", "home", body, as_of=as_of, sources=[("dailies", "daily/*"), ("situations", "theaters/index.json"), ("pulses", "snapshots/latest"), ("calendar", "calendar/next.json"),
                                                                 ("sanctions", "sanctions/recent.json"), ("actors", "actors/*.json")])]
