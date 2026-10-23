"""
``build_all``: run the builders over one context and return every view with the problems found.

Families run in dependency order (the shared graph first; the search index last, because it only points at views this run emits). A builder that fails is
reported and skipped - the previous view of its family stays published - and never stops the others. A view over its family's byte budget is reported and
is not published.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import country, daily_hub, entity, event, graph, home, hud, search, series, situation
from .base import View
from .context import ViewContext

#: family name (the ``--only`` selector and the manifest key) -> builder. `situation` also emits the `situations` index.
BUILDERS: dict[str, Callable[[ViewContext], list[View]]] = {
    "graph": graph.build,
    "country": country.build,
    "situation": situation.build,
    "event": event.build,
    "entity": entity.build,
    "series": series.build,                  # also emits `series-index`
    "home": home.build,
    "hud": hud.build,
    "daily-hub": daily_hub.build,
}
#: Families that only read the staged documents and tables (no corpus): the fast job builds these every half hour.
FAST = ("home", "hud", "daily-hub")
ALL = (*BUILDERS, "search-index")


@dataclass
class Result:
    views: list[View] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    over_budget: list[str] = field(default_factory=list)
    seconds: dict[str, float] = field(default_factory=dict)

    def ok_views(self) -> list[View]:
        bad = set(self.over_budget)
        return [v for v in self.views if v.path not in bad]


def build_all(ctx: ViewContext, only: list[str] | None = None) -> Result:
    names = [n for n in ALL if not only or n in only]
    unknown = sorted(set(only or []) - set(ALL))
    res = Result(errors=[f"unknown view family {u!r}; one of {', '.join(ALL)}" for u in unknown])
    for name in names:
        t0 = time.perf_counter()
        try:
            if name == "search-index":
                built = search.build(ctx, {v.key for v in res.views})
            else:
                built = BUILDERS[name](ctx)
        except Exception as exc:  # noqa: BLE001 - the family's previous views stay published
            res.errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        finally:
            res.seconds[name] = round(time.perf_counter() - t0, 2)
        for v in built:
            if (why := v.over_budget()):
                res.over_budget.append(v.path)
                res.errors.append(why)
            res.views.append(v)
    if not only or len(names) == len(ALL):
        res.views.append(manifest(res.views, ctx))
    return res


def manifest(views: list[View], ctx: ViewContext) -> View:
    """``views/manifest.json``: what exists, per family (count, bytes, schema, the largest). Small by construction: it lists families, not keys."""
    from .base import make

    fams: dict[str, dict] = {}
    for v in views:
        f = fams.setdefault(v.family, {"schema": v.body["schema"], "count": 0, "bytes": 0, "largest": {"key": "", "bytes": 0}})
        n = v.size()
        f["count"] += 1
        f["bytes"] += n
        if n > f["largest"]["bytes"]:
            f["largest"] = {"key": v.key, "bytes": n}
    as_of = max((str(v.body.get("as_of") or "") for v in views), default="")
    return make("manifest", "manifest", {"families": fams, "count": sum(f["count"] for f in fams.values())}, as_of=as_of, sources=[("views", "this build")])
