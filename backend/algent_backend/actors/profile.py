"""
Profile, compare, evidence — the readers of the actors store.

``profile(iso2)`` is one actor as grouped fields (People, Economy, Trade, Energy, Military) each with
its latest value, the year it is for and where it came from, plus leadership and nuclear status and the
world rank of the headline numbers. ``compare`` lines actors up on shared scales. ``evidence_block`` is
one compact cited line per actor for a writer's prompt (not wired into the desk yet).

Ranks are over STATES only (territories and blocs are shown but never ranked), each state at its own
latest year: a small year mismatch between countries is real and each figure carries its year.
Nothing here fetches; an empty store yields empty groups, never an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import catalog, registry, store
from .contracts import Leaders, Observation
from .format import figure
from .nuclear import nuclear

HEADLINE = ("population", "gdp", "gdp_pc", "energy_production", "milex")
COMPARE = ("population", "gdp", "gdp_pc", "energy_production", "energy_use", "milex", "milex_pct", "armed_forces")
FUELS = ("oil", "gas", "coal")
GROUPS = ("people", "economy", "trade", "energy", "military")

#: A derived field (no indicator of its own): label, unit and the indicators it sums.
_DERIVED = {"energy_production": ("Fossil fuel production (oil + gas + coal)", "twh", "energy", ("oil_prod", "gas_prod", "coal_prod"))}


@dataclass
class Corpus:
    """The store's current picture, loaded once: latest observation per indicator per country, and leaders."""
    latest: dict[str, dict[str, Observation]] = field(default_factory=dict)
    leaders: dict[str, Leaders] = field(default_factory=dict)
    _ranks: dict[str, dict[str, tuple[int, int]]] = field(default_factory=dict)

    def value(self, indicator: str, iso2: str) -> tuple[float, int, str] | None:
        """(value, year, source) for an indicator or derived field; None when nothing is stored."""
        if indicator in _DERIVED:
            parts = [self.latest.get(i, {}).get(iso2) for i in _DERIVED[indicator][3]]
            have = [o for o in parts if o is not None]
            return (sum(o.value for o in have), max(o.year for o in have), "owid") if have else None
        o = self.latest.get(indicator, {}).get(iso2)
        return (o.value, o.year, o.source) if o else None

    def rank(self, indicator: str, iso2: str) -> tuple[int, int] | None:
        """(rank from the top, how many states are ranked) among states; None for a non-state or no value."""
        if indicator not in self._ranks:
            vals = {c.iso2: v[0] for c in registry.states() if (v := self.value(indicator, c.iso2))}
            order = sorted(vals, key=lambda k: (-vals[k], k))
            self._ranks[indicator] = {k: (i + 1, len(order)) for i, k in enumerate(order)}
        return self._ranks[indicator].get(iso2)


def load_corpus() -> Corpus:
    return Corpus(latest={i.id: store.latest(i.id) for i in catalog.INDICATORS}, leaders=store.latest_leaders())


def _field(corpus: Corpus, indicator: str, iso2: str) -> dict[str, Any] | None:
    got = corpus.value(indicator, iso2)
    if got is None:
        return None
    if indicator in _DERIVED:
        label, unit, group = _DERIVED[indicator][:3]
        base = {"id": indicator, "label": label, "unit": unit, "group": group}
    else:
        ind = catalog.get(indicator)
        base = {"id": ind.id, "label": ind.label, "unit": ind.unit, "group": ind.group}
    return {**base, "value": got[0], "year": got[1], "source": got[2]}


def _energy_role(corpus: Corpus, iso2: str) -> dict[str, list[str]]:
    """Per fuel, surplus / deficit by the plain sign of production minus consumption (no cut-offs; NOT trade: the two series are measured differently, so a surplus is "produces more than it uses", not "exports"); a fuel
    missing either side is left out (OWID carries consumption by fuel for far fewer countries than production)."""
    out: dict[str, list[str]] = {"surplus": [], "deficit": []}
    for fuel in FUELS:
        prod, cons = corpus.value(f"{fuel}_prod", iso2), corpus.value(f"{fuel}_cons", iso2)
        if prod is None or cons is None:
            continue
        p, c = prod[0], cons[0]
        if p > c:
            out["surplus"].append(fuel)
        elif c > p:
            out["deficit"].append(fuel)
    return out


def _official(row: Leaders | None, office: str) -> dict[str, str] | None:
    o = getattr(row, office, None) if row else None
    return {"name": o.name, "since": o.since} if o else None


def profile(iso2: str, corpus: Corpus | None = None) -> dict[str, Any]:
    """One actor, grouped. Unknown country -> ``{}``; a known one with no stored data -> empty groups."""
    country = registry.get(iso2)
    if country is None:
        return {}
    corpus = corpus or load_corpus()
    code = country.iso2
    groups: dict[str, list[dict[str, Any]]] = {g: [] for g in GROUPS}
    for ind in catalog.INDICATORS:
        if (f := _field(corpus, ind.id, code)):
            groups[ind.group].append(f)
    if (f := _field(corpus, "energy_production", code)):
        groups["energy"].insert(0, f)
    headline = []
    for ind_id in HEADLINE:
        f = _field(corpus, ind_id, code)
        if f and (r := corpus.rank(ind_id, code)):
            f = {**f, "rank": r[0], "of": r[1], "percentile": int(100 * (r[1] - r[0]) / r[1])}
        if f:
            headline.append(f)
    leaders = corpus.leaders.get(code)
    return {"iso2": code, "iso3": country.iso3, "name": country.name, "region": country.region,
            "capital": country.capital, "kind": country.kind, "headline": headline, "groups": groups,
            "energy_role": _energy_role(corpus, code),
            "leadership": {"head_of_state": _official(leaders, "head_of_state"),
                           "head_of_government": _official(leaders, "head_of_government"),
                           "as_of": leaders.fetched_at[:10] if leaders else "", "nuclear": nuclear(code)}}


def compare(iso2s: list[str], corpus: Corpus | None = None) -> dict[str, Any]:
    """Actors side by side: per metric every actor's value on one shared scale (``max`` = the largest shown)."""
    corpus = corpus or load_corpus()
    codes = [c.iso2 for c in (registry.get(i) for i in iso2s) if c]
    metrics = []
    for ind_id in COMPARE:
        rows = []
        for code in codes:
            f = _field(corpus, ind_id, code)
            if f:
                r = corpus.rank(ind_id, code)
                rows.append({"iso2": code, "value": f["value"], "year": f["year"], "rank": r[0] if r else None})
        if rows:
            f0 = _field(corpus, ind_id, rows[0]["iso2"]) or {}
            metrics.append({"id": ind_id, "label": f0.get("label", ind_id), "unit": f0.get("unit", "number"),
                            "max": max(r["value"] for r in rows), "rows": rows})
    return {"actors": [{"iso2": c, "name": registry.display_name(c)} for c in codes], "metrics": metrics}


def _line(p: dict[str, Any]) -> str:
    def f(item: dict[str, Any] | None) -> str:
        return f"{figure(item['value'], item['unit'])} ({item['year']})" if item else ""

    by_id = {x["id"]: x for g in p["groups"].values() for x in g}
    lead = p["leadership"]
    led = [f"{o['name']} ({role})" for role, o in (("head of state", lead["head_of_state"]),
                                                    ("head of government", lead["head_of_government"])) if o]
    if len(led) == 2 and lead["head_of_state"]["name"] == lead["head_of_government"]["name"]:
        led = [f"{lead['head_of_state']['name']} (head of state and government)"]
    bits = []
    if led:
        bits.append("led by " + ", ".join(led))
    if (x := f(by_id.get("population"))):
        bits.append(f"population {x}")
    if (x := f(by_id.get("gdp"))):
        bits.append(f"GDP {x}" + (f", {figure(by_id['gdp_pc']['value'], 'usd')} per person" if "gdp_pc" in by_id else ""))
    role, parts = p["energy_role"], []
    if role["surplus"]:
        parts.append("produces more than it uses: " + ", ".join(role["surplus"]))
    if role["deficit"]:
        parts.append("uses more than it produces: " + ", ".join(role["deficit"]))
    if parts and (prod := by_id.get("energy_production")):
        bits.append(f"energy: {'; '.join(parts)}; fossil production {f(prod)}")
    elif (x := f(by_id.get("energy_use"))):
        bits.append(f"energy use {x}")
    if (mil := by_id.get("milex")):
        pct = by_id.get("milex_pct")
        bits.append(f"military spending {f(mil)}" + (f" = {figure(pct['value'], 'pct')} of GDP" if pct else ""))
    if lead["nuclear"]:
        n = lead["nuclear"]
        bits.append(f"nuclear: about {n['stockpile']:,} warheads in military stockpile (FAS {n['year']})")
    return f"- {p['name']} ({p['iso2']}): " + "; ".join(bits) if bits else f"- {p['name']} ({p['iso2']}): no stored data"


def evidence_block(iso2s: list[str], corpus: Corpus | None = None) -> str:
    """One cited line per actor for a writer's prompt; empty string when none of the codes is a known country."""
    corpus = corpus or load_corpus()
    lines = [_line(p) for i in iso2s if (p := profile(i, corpus))]
    if not lines:
        return ""
    return ("ACTORS ON RECORD (World Bank/SIPRI, Our World in Data, Wikidata, FAS; year in brackets; "
            "leaders as of last check)\n" + "\n".join(lines))
