"""
``views/daily-hub.json``: the Daily hub page. One card per desk: the newest report as a digest (headline, parts of the day, section rows), its date and
how many days the archive holds. The hub is navigation, so it never needed the 800 KB report it used to load per desk.
"""

from __future__ import annotations

from . import flags
from .base import View, make
from .context import ViewContext
from .digest import digest

RECENT_DAYS = 6                 # the hub lists this many days after today's (components: app/daily/page.tsx RECENT_DAYS)


def build(ctx: ViewContext) -> list[View]:
    desks = []
    for desk in flags.DESKS:
        dates = ctx.daily_dates(str(desk["id"]))
        report = ctx.daily(str(desk["id"]), dates[0]) if dates else None
        desks.append({"desk": desk["id"], "date": dates[0] if dates else "", "dates_total": len(dates), "recent": dates[1: RECENT_DAYS + 1],
                      "report": digest(report) if report else None})
    as_of = max((d["date"] for d in desks), default="")
    return [make("daily-hub", "daily-hub", {"desks": desks}, as_of=as_of, sources=[("dailies", "daily/*")])]
