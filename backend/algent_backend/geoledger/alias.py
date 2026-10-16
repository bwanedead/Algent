"""
Names that mean one plant: the alias layer in front of ``match.find``.

``match`` already folds spellings (transliteration, y/i, -ska endings, plant-kind words dropped) and refuses a wrong unit
number. This layer adds what folding cannot:

* **Curated groups** (``alias_data.CURATED``): "Trypilska TES" = "Trypillya TPP", "Darnytska CHP" = "Kyiv CHP-4".
* **Unit-only names** ("CHP-5", "ТЕЦ-5", "TETs-5": a plant kind and a number, no place). With a place given they become
  "Kyiv CHP-5"; without one they resolve only when exactly ONE plant of that kind and number exists in the country,
  and two such plants resolve to nothing (a duplicate is cheaper than a wrong merge).

Extraction calls ``find`` here, so a spelling the ledger already knows never mints a second asset. Docs:
docs/architecture/geoledger.md ("Aliases and merges").
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from . import match
from .alias_data import CURATED
from .contracts import Asset

Sig = tuple[tuple[str, ...], tuple[str, ...], str]       # (content words stemmed, unit numbers, plant kind)
UnitKey = tuple[str, str, str]                            # (country, plant kind, unit number)


def sig(name: str) -> Sig | None:
    """What identifies a name once script, spelling and ending are folded; None when it has no content word."""
    words, nums = match.tokens(name)
    if not words:
        return None
    return tuple(sorted(match.stem(w) for w in words)), tuple(sorted(nums)), match.plant_class(name)


@lru_cache(maxsize=1)
def _groups() -> tuple[tuple[tuple[str, ...], frozenset[Sig]], ...]:
    return tuple((g, frozenset(s for n in g if (s := sig(n)) is not None)) for g in CURATED)


def unit_only(name: str) -> tuple[str, str] | None:
    """(plant kind, unit number) of a name that is only a kind and one number ("ТЕЦ-5"); None for anything else."""
    words, nums = match.tokens(name)
    cls = match.plant_class(name)
    return (cls, next(iter(nums))) if not words and cls and len(nums) == 1 else None


def unit_keys(a: Asset) -> list[tuple[str, str]]:
    """The (plant kind, unit number) each name of a power plant carries ("Kyiv CHP-5" -> thermal, 5)."""
    if a.type != "power_plant":
        return []
    out = []
    for n in (a.name, *a.aliases):
        _, nums = match.tokens(n)
        if (cls := match.plant_class(n)) and len(nums) == 1:
            out.append((cls, next(iter(nums))))
    return out


def variants(names: Iterable[str], place: str = "") -> list[str]:
    """The names as written, then their curated siblings, then place-qualified forms of unit-only names."""
    base = [n.strip() for n in names if n and n.strip()]
    sigs = {s for n in base if (s := sig(n)) is not None}
    out = list(base)
    for members, member_sigs in _groups():
        if sigs & member_sigs:
            out += members
    if place.strip():
        out += [f"{place.strip()} {n}" for n in base if unit_only(n)]
    return list(dict.fromkeys(out))


def find(index, names: list[str], *, type_: str = "other", country: str = "", at: tuple[float, float] | None = None,
         place: str = "") -> match.Match:
    """``match.find`` over the name's variants, then the unit-only rule (``index.by_unit``) when the name is only "CHP-5"."""
    forms = variants(names, place)
    hit = match.find(index, forms, type_=type_, country=country, at=at)
    if hit.asset is not None or hit.reason == "ambiguous":
        return hit
    by_unit = getattr(index, "by_unit", None)
    if by_unit is None or not country or type_ not in ("power_plant", "other"):
        return hit
    for n in forms:
        if (u := unit_only(n)) is not None:
            found = by_unit(country, *u)
            if len(found) == 1:
                return match.Match(found[0], 0.9, "")
            if found:
                return match.Match(None, 0.0, "ambiguous")
    return hit
