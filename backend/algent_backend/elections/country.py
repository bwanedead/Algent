"""The country an election article is about, from its title ("2026 Hungarian parliamentary election" -> HU). Titles use demonyms, which the country table does not
know, so a word is matched by its first five letters against the country names and counts only when exactly one country answers (Niger / Nigeria stay unknown)."""

from __future__ import annotations

import re

from algent_backend.actors import names, registry

_SKIP = frozenset("election elections general presidential parliamentary legislative national referendum senate house united states local regional primary".split())


def of(title: str) -> str:
    """ISO2 of the country the title names, or ""."""
    if re.search(r"gubernatorial|United States|House of Representatives", title):          # a US state's name ("Georgia") is not a country here
        return "US"
    words = [w for w in re.findall(r"[A-Za-z]{4,}", title) if w.casefold() not in _SKIP]
    for w in words:
        if (iso := names.iso2(w)):
            return iso
    table = registry.load()
    for w in words:
        hit = {c.iso2 for c in table.values() if c.name.casefold()[:5] == w.casefold()[:5]}
        if len(hit) == 1:
            return hit.pop()
    if re.search(r"\bUnited States\b", title):
        return "US"
    return ""
