"""
Countries and the state profiles: the country table (``actors.registry``) declares every country (and capital) once, with the aliases every other
source's names resolve through; the actors store adds who leads each one (relations, dated) and the yearly indicator series (observations).
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.actors import catalog, registry, store

from .. import flags
from ..norm import slug
from ..sink import Sink
from .base import Source, Unit, digest_of, mark


def country_id(iso2: str) -> str:
    return f"country:{iso2.upper()}"


def _registry_fp() -> str:
    return digest_of(sorted((c.iso2, c.name, c.iso3, c.capital, c.region, c.kind, sorted(c.aliases)) for c in registry.load().values()))


def _countries() -> Iterator[Unit]:
    table = registry.load()
    fp = _registry_fp()

    def emit(sink: Sink) -> None:
        for c in sorted(table.values(), key=lambda c: c.iso2):
            sink.declare(country_id(c.iso2), "country", c.name, aliases=[*c.aliases, c.iso3, c.iso2], iso2=c.iso2, rank=flags.RANK_AUTHORITY,
                         attrs={"iso3": c.iso3, "region": c.region, "territory": c.kind != "state"})
            if c.capital and registry.resolve(c.capital) is None:             # a capital named like a country ("Singapore") stays the country
                sink.declare(f"place:capital:{c.iso2}", "place", c.capital, iso2=c.iso2, rank=flags.RANK_AUTHORITY,
                             attrs={"capital_of": c.iso2, "kind": "city"})
                sink.relation("capital_of", src=f"place:capital:{c.iso2}", dst=country_id(c.iso2))

    yield Unit("registry:countries", fp, emit, path="actors/countries.json")


def person_id(name: str) -> str:
    return f"person:{slug(name)}"


def _leaders() -> Iterator[Unit]:
    rows = store.leaders_log()
    fp = digest_of([r.model_dump() for r in rows])

    def emit(sink: Sink) -> None:
        for r in rows:
            for rel, off in (("head_of_state", r.head_of_state), ("head_of_government", r.head_of_government)):
                if off is None or not off.name:
                    continue
                pid = person_id(off.name)
                sink.declare(pid, "person", off.name, attrs={"wikidata": off.id} if off.id else None)
                sink.relation(rel, src=country_id(r.iso2), dst=pid, date=off.since or r.fetched_at, note=f"since {off.since}" if off.since else "")
    yield Unit("actors:leaders", fp, emit, path="actors_store/leaders.jsonl")


def _indicators() -> Iterator[Unit]:
    for ind_id in store.stored_ids():
        try:
            ind = catalog.get(ind_id)
        except KeyError:
            continue
        rows = store.history(ind_id)
        fp = digest_of([(o.iso2, o.year, o.value) for o in rows])

        def emit(sink: Sink, rows=rows, ind=ind) -> None:
            for o in rows:
                sink.observation(ind.id, str(o.year), o.value, entity=country_id(o.iso2), unit=ind.unit, basis="official", label=ind.label,
                                 source_url=o.source_url, note=f"{o.source}{' (revised)' if o.revised else ''}")
        yield Unit(f"actors:indicator:{ind_id}", fp, emit, path=f"actors_store/obs/{ind_id}.jsonl")


def _units() -> Iterator[Unit]:
    yield from _countries()
    yield from _leaders()
    yield from _indicators()


def _watermark() -> str:
    root = store.store_dir()
    stores = mark([root / "leaders.jsonl", *(root / "obs").glob("*.jsonl")]) if root.is_dir() else "none"
    return f"{stores}:{_registry_fp()}"


SOURCE = Source("actors", "actors", _units, _watermark)
