"""
``views/entity/<kind>/<id>.json``: one file per entity with substance (people, organisations, places and assets, vessels, labs, models, speakers), straight from the
corpus index. It is what ``entity(name)``, ``about``, ``timeline``, ``related`` and ``series`` answer from for an agent, and what the place pages render.

Every record keeps its provenance (``product``, ``origin`` and the source URLs) and every series its ``basis`` (the stats-registry vocabulary). Countries and
situations have views of their own (``country/``, ``situation/``); a country is still found by name through the search index.

Which entities: those the record says something about (``SEARCH_MIN_USES`` or more mentions, events, relations or series), most-used first, capped at
``ENTITY_VIEWS_MAX`` so a runaway corpus cannot turn into a runaway number of objects. A place the geoledger holds with status events always has one.
"""

from __future__ import annotations

import re
from typing import Any

from . import dailies, flags
from .base import View, make
from .context import ViewContext

#: Kinds that get an entity view (countries/situations have their own families; pulses, markets and free-text topics are not "things").
KINDS = ("person", "org", "actor", "place", "vessel", "lab", "model")
ENTITY_VIEWS_MAX = 12000
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def entity_key(entity_id: str, kind: str) -> str:
    """The view key of an entity: ``entity/<kind>/<id without its kind prefix, made path-safe>``. A digest is added when making it safe lost something."""
    raw = entity_id.split(":", 1)[1] if ":" in entity_id else entity_id
    safe = _SAFE.sub("_", raw).strip("_") or "x"
    if safe != raw:
        import hashlib

        safe = f"{safe[:60]}-{hashlib.sha1(entity_id.encode('utf-8')).hexdigest()[:6]}"
    return f"entity/{kind}/{safe}"


_USES = """
WITH u AS (
  SELECT entity_id AS id, COUNT(*) AS n FROM mentions WHERE entity_id IS NOT NULL GROUP BY 1
  UNION ALL SELECT entity_id, COUNT(*) FROM event_actors WHERE entity_id IS NOT NULL GROUP BY 1
  UNION ALL SELECT place_id, COUNT(*) FROM events WHERE place_id IS NOT NULL GROUP BY 1
  UNION ALL SELECT src_id, COUNT(*) FROM relations WHERE src_id IS NOT NULL GROUP BY 1
  UNION ALL SELECT dst_id, COUNT(*) FROM relations WHERE dst_id IS NOT NULL GROUP BY 1
  UNION ALL SELECT entity_id, COUNT(DISTINCT metric) FROM observations WHERE entity_id != '' GROUP BY 1)
SELECT e.id, e.kind, e.name, SUM(u.n) AS uses FROM entities e JOIN u ON u.id = e.id WHERE e.kind IN ({kinds}) GROUP BY e.id
"""


def usage(db: Any) -> dict[str, int]:
    """``{entity id: how much the record says about it}`` for every entity of the kinds that get a view."""
    marks = ",".join("?" * len(KINDS))
    return {r["id"]: int(r["uses"]) for r in db.execute(_USES.format(kinds=marks), KINDS)}


def candidates(ctx: ViewContext) -> list[tuple[str, int]]:
    """Entity ids to publish with their usage, most-used first (ties by id so the cut is stable)."""
    if ctx.corpus is None:
        return []
    uses = usage(ctx.corpus.db)
    keep = [(i, n) for i, n in uses.items() if n >= flags.SEARCH_MIN_USES or i.startswith("asset:")]
    keep.sort(key=lambda x: (-x[1], x[0]))
    return keep[:ENTITY_VIEWS_MAX]


def _strip(obj: Any) -> Any:
    """Drop ``ingested_at`` everywhere: it changes on a full rebuild without the record changing, and would re-upload every view for nothing."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k != "ingested_at"}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def _slim_series(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**{k: s.get(k) for k in ("metric", "label", "unit", "basis", "n", "first", "last", "product")},
             "points": [[ts, v] for ts, v in s.get("points", [])[-flags.SERIES_POINTS:]], "latest": s.get("latest")} for s in series]


def _place_block(ctx: ViewContext, entity_id: str) -> dict[str, Any] | None:
    """A geoledger place: its asset row and whole status history, and the theaters whose reports put it there (each event's ``via``)."""
    if not entity_id.startswith("asset:"):
        return None
    doc = ctx.table(f"geo/a/{entity_id[6:]}.json")
    if not isinstance(doc, dict) or not isinstance(doc.get("asset"), dict):
        return None
    events = sorted(dailies.objs(doc.get("events")), key=lambda e: (str(e.get("occurred_on")), str(e.get("observed_at"))))[:500]
    via = {m.group(1) for e in events if (m := re.match(r"daily:\d{4}-\d{2}-\d{2}:([\w.-]+)", str(e.get("via") or "")))}
    from . import graph

    refs = graph.shared(ctx)["refs"]
    return {"asset": doc["asset"], "history": events, "theaters": [refs.get(t) or {"id": t, "name": t, "direction": "unclear", "band": "unassessed", "linked": False} for t in sorted(via)]}


def build_one(ctx: ViewContext, entity_id: str, uses: int) -> View | None:
    from algent_backend.corpus.query import about as q_about
    from algent_backend.corpus.query import entity as q_entity
    from algent_backend.corpus.query import graph as q_graph
    from algent_backend.corpus.query import resolve, series as q_series

    db = ctx.corpus.db
    row = db.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if row is None:
        return None
    e = resolve.shape(row)
    prof = q_entity.profile(db, e, timeline_n=flags.ENTITY_EVENTS)
    got = q_about.about(db, entity_id, limit=flags.ENTITY_DOCS)
    merged = [r[0] for r in db.execute("SELECT old_id FROM entity_merge WHERE canon_id = ? ORDER BY old_id", (entity_id,))]
    body = {
        "id": entity_id, "kind": e["kind"], "name": e["name"], "aliases": e["aliases"][:20], "iso2": e.get("iso2"), "lat": e.get("lat"), "lon": e.get("lon"),
        "attrs": {k: v for k, v in (e.get("attrs") or {}).items() if isinstance(v, (str, int, float, bool))}, "also_known_as_ids": merged, "uses": uses,
        "counts": prof["counts"], "latest": prof["latest"], "situations": prof["situations"], "relations": prof["relations"][: flags.ENTITY_RELATED],
        "related": q_graph.related(db, entity_id, limit=flags.ENTITY_RELATED), "timeline": prof["timeline"],
        "documents": got["documents"][: flags.ENTITY_DOCS], "claims": got["claims"][: flags.ENTITY_CLAIMS], "events": got["events"][: flags.ENTITY_EVENTS],
        "series": _slim_series(q_series.series(db, entity_id=entity_id, limit=flags.SERIES_PER_ENTITY)),
    }
    place = _place_block(ctx, entity_id)
    if place:
        body["place"] = place
    as_of = max([str(d.get("date") or "") for d in body["documents"]] + [str(ev.get("date") or "") for ev in body["events"]] or [""])
    return make("entity", entity_key(entity_id, e["kind"]), _strip(body), as_of=as_of,
                sources=[("corpus_index", f"entity {entity_id}"), *([("geoledger", f"geo/a/{entity_id[6:]}.json")] if place else [])])


def build(ctx: ViewContext) -> list[View]:
    out = []
    for entity_id, uses in candidates(ctx):
        try:
            v = build_one(ctx, entity_id, uses)
        except Exception as exc:  # noqa: BLE001 - one entity that cannot be summarised must not lose the others
            print(f"[views] entity {entity_id}: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            continue
        if v is not None:
            out.append(v)
    return out
