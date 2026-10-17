"""Country names that official lists use -> ISO2 via the one country table (``actors.registry``); unknown names are dropped."""

from __future__ import annotations

from collections.abc import Iterable

#: Spellings the lists use that the table does not know as aliases.
_EXTRA = {"burma (myanmar)": "MM", "korea, north": "KP", "korea, south": "KR", "iran (islamic republic of)": "IR",
          "the gambia": "GM", "congo, democratic republic of the": "CD", "congo, republic of the": "CG",
          "palestinian territories": "PS", "west bank": "PS", "gaza strip": "PS", "crimea": "UA"}


def iso2(name: str) -> str | None:
    from algent_backend.actors import registry

    raw = " ".join((name or "").split())
    if not raw:
        return None
    if len(raw) == 2 and raw.isalpha() and registry.get(raw.upper()):
        return raw.upper()
    return _EXTRA.get(raw.casefold()) or registry.resolve(raw)


def many(names: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for n in names:
        if (c := iso2(n)):
            seen.setdefault(c)
    return list(seen)
