"""
The Actors on the site — one JSON per published actor plus an index, as part of the desk snapshot.

Written by ``intel_page.write_intel`` to ``content/intel/actors/<ISO2>.json`` (what the site reads) and
``public/data/actors/<ISO2>.json`` (the agent feed), plus ``index.json`` in both::

    index = {"schema":"ohmega.actor.index/1","data_as_of":"YYYY-MM-DD","actors":[{"iso2","name","region",
        "population","gdp","gdp_pc","energy_production","milex":{"value","unit","year"}|null,
        "theaters":int,"statements":int,"url":"/intel/actors/<ISO2>","data_url":"/data/actors/<ISO2>.json"}]}
        // alphabetical; the headline figures are the profile's, each on its own year
    actor = {"schema":"ohmega.actor/1","iso2","iso3","name","region","capital","kind","data_as_of",
        **actors.profile(iso2),   // headline[] (value, year, rank, of, percentile), groups{people,economy,trade,
                                  // energy,military}[{id,label,unit,group,value,year,source}], energy_role,
                                  // leadership{head_of_state,head_of_government,as_of,nuclear}
        "statements":[{"id","speaker","role","date","text","is_quote","signal","stance","source_url"}],  // newest 8
        "involved":{"theaters":[{"id","name","mentions"}],"pulses":[{"id","name","band","position","theater_id"}]},
        "credits":[{"source","name","licence","url","years":"2024" | "2020-2025"}],"url","data_url"}

WHICH actors (bounded): the G20 states and the UN Security Council's permanent five, always; plus the
countries the desk's own records NAME, up to ``MAX_REFERENCED``, ranked by theaters involved then
statements. "Name" is resolved the semantic way available: a theater dossier's ``actors`` and
``relations`` (which the daily/brief writers already chose), its validated ``places[].country``, and a
statement's ``affiliation`` (set by the extractor) are each passed through ``actors.registry.resolve``,
which maps a NAME to a country and never scans prose. Headlines are never regexed. Pulses carry no actor
field, so a Pulse reaches an actor through its theater: the theater's Pulses are listed as involved.
An actor with nothing stored (no leaders, no figures) is skipped. ``data_as_of`` is the store's newest
fetch date, not the wall clock, so an unchanged store publishes byte-identical files. Never raises.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from algent_backend.actors import catalog, registry, store
from algent_backend.actors.profile import HEADLINE, Corpus, load_corpus, profile

SCHEMA = "ohmega.actor/1"
INDEX_SCHEMA = "ohmega.actor.index/1"
MAX_REFERENCED = 60
MAX_STATEMENTS = 8
MAX_PULSES = 10


def actor_url(iso2: str) -> str:
    return f"/intel/actors/{iso2}"


def actor_data_url(iso2: str) -> str:
    return f"/data/actors/{iso2}.json"


def _named_in(dossier: dict) -> Counter:
    """ISO2 -> how often this theater's own records name the country (actors, relations, validated places)."""
    hits: Counter = Counter()
    for a in dossier.get("actors") or []:
        if (iso := registry.resolve(str(a.get("name") or ""))):
            hits[iso] += max(1, int(a.get("mentions") or 1))
    for r in dossier.get("relations") or []:
        for end in ("source", "target"):
            if (iso := registry.resolve(str(r.get(end) or ""))):
                hits[iso] += max(1, int(r.get("count") or 1))
    for p in dossier.get("places") or []:
        if (iso := registry.resolve(str(p.get("country") or ""))):
            hits[iso] += max(1, int(p.get("count") or 1))
    return hits


def _involvement(dossiers: dict[str, dict]) -> dict[str, dict[str, list[dict]]]:
    """{iso2: {"theaters": [...], "pulses": [...]}} from every dossier."""
    out: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"theaters": [], "pulses": []})
    for tid, d in sorted(dossiers.items()):
        for iso, n in _named_in(d).items():
            out[iso]["theaters"].append({"id": tid, "name": d.get("name", tid), "mentions": n})
            out[iso]["pulses"] += [{"id": p["id"], "name": p.get("name", ""), "band": p.get("band", "unassessed"),
                                    "position": p.get("position"), "theater_id": tid} for p in d.get("pulses") or []]
    for row in out.values():
        row["theaters"].sort(key=lambda t: (-t["mentions"], t["name"]))
        seen: set[str] = set()
        row["pulses"] = [p for p in sorted(row["pulses"], key=lambda p: (p["position"] is None, -(p["position"] or 0)))
                         if not (p["id"] in seen or seen.add(p["id"]))][:MAX_PULSES]
    return out


def _statements() -> dict[str, list[dict]]:
    """Newest statements per actor, by the speaker's affiliation resolved through the registry."""
    from algent_backend.agent_system.agents.statements import store as statements

    by: dict[str, list[dict]] = defaultdict(list)
    for s in statements.query():                       # newest first
        iso = registry.resolve(s.affiliation)
        if iso and len(by[iso]) < MAX_STATEMENTS:
            by[iso].append({"id": s.id, "speaker": s.speaker, "role": s.role, "date": s.date,
                            "text": s.quote or s.paraphrase, "is_quote": bool(s.quote), "signal": s.signal,
                            "stance": s.stance, "source_url": s.source_url})
    return by


def _credits(p: dict[str, Any]) -> list[dict[str, str]]:
    years: dict[str, list[int]] = defaultdict(list)
    for g in p["groups"].values():
        for f in g:
            years[f["source"]].append(f["year"])
    if p["leadership"]["head_of_state"] or p["leadership"]["head_of_government"]:
        years["wikidata"].append(0)
    if p["leadership"]["nuclear"]:
        years["nuclear"].append(p["leadership"]["nuclear"]["year"])
    out = []
    for key, ys in years.items():
        src, ys = catalog.SOURCES[key], sorted(y for y in ys if y)
        span = "" if not ys else str(ys[0]) if ys[0] == ys[-1] else f"{ys[0]}-{ys[-1]}"
        out.append({"source": key, "name": src.name, "licence": src.licence, "url": src.url, "years": span})
    return sorted(out, key=lambda c: c["source"])


def _index_row(a: dict) -> dict:
    head = {h["id"]: {"value": h["value"], "unit": h["unit"], "year": h["year"]} for h in a["headline"]}
    return {"iso2": a["iso2"], "name": a["name"], "region": a["region"],
            **{k: head.get(k) for k in HEADLINE}, "theaters": len(a["involved"]["theaters"]),
            "statements": len(a["statements"]), "url": a["url"], "data_url": a["data_url"]}


def select(dossiers: dict[str, dict], statements: dict[str, list[dict]]) -> list[str]:
    """The published set: G20 + P5, then the most-involved named countries up to ``MAX_REFERENCED``."""
    standing = [c for c in dict.fromkeys([*registry.G20, *registry.UNSC_P5]) if registry.get(c)]
    involved = _involvement(dossiers)
    named = {iso: (len(row["theaters"]), len(statements.get(iso, []))) for iso, row in involved.items()}
    for iso in statements:
        named.setdefault(iso, (0, len(statements[iso])))
    extra = sorted((i for i in named if i not in standing and (c := registry.get(i)) and c.kind != "bloc"),
                   key=lambda i: (-named[i][0], -named[i][1], i))[:MAX_REFERENCED]
    return [*standing, *extra]


def build_actor_files(dossiers: dict | None, corpus: Corpus | None = None) -> dict[str, dict]:
    """``{"index.json": ..., "<ISO2>.json": ...}`` for the published actors, or ``{}`` when the store holds
    nothing (or anything fails: this is a view onto stores that are already safe, so a fault here must never
    cost the rest of the publish)."""
    try:
        corpus = corpus or load_corpus()
        if not any(corpus.latest.values()) and not corpus.leaders:
            return {}
        theaters = (dossiers or {}).get("theaters") or {}
        said, involved = _statements(), _involvement(theaters)
        as_of, files = store.data_as_of(), {}
        for iso in select(theaters, said):
            p = profile(iso, corpus)
            if not p or not (p["leadership"]["head_of_state"] or p["headline"] or any(p["groups"].values())):
                continue
            files[f"{iso}.json"] = {"schema": SCHEMA, "data_as_of": as_of, **p, "statements": said.get(iso, []),
                                    "involved": involved.get(iso, {"theaters": [], "pulses": []}),
                                    "credits": _credits(p), "url": actor_url(iso), "data_url": actor_data_url(iso)}
        index = {"schema": INDEX_SCHEMA, "data_as_of": as_of,
                 "actors": sorted((_index_row(a) for a in files.values()), key=lambda r: r["name"])}
        return {"index.json": index, **files} if files else {}
    except Exception as exc:  # noqa: BLE001
        print(f"[intel] actors not built: {type(exc).__name__}: {str(exc)[:160]}", flush=True)
        return {}
