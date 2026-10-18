"""
Desk domains — what makes one daily's world different from another's.

The recipe (heat board -> focus -> sections -> summary -> publish) is the same for every domain; a domain only supplies DATA:

* ``loaders``  — the headline classes its board is made of (geopolitics: our radar, Wikipedia Current Events, the library minus the AI
  sources; AI: the AI sources in the library, and what AI practitioners discuss). Each class is a separate denominator for coverage shares.
* ``topics``   — standing topic areas. They are LENSES shown to the clustering and the writers ("watch for these dynamics"), not buckets and
  not theaters: a theater is still whatever persistent dynamic the headlines show, and a topic with nothing going on yields none.
* ``uses_radar`` — whether the newsroom's radar editions are part of the base (they are the geopolitics desk's own picks).

A board is stored per domain (``boards/`` for geopolitics, the historical location; ``boards/<domain>/`` otherwise), theaters carry the domain,
and ``focus.plan`` / ``desk.pick_theaters`` already filter by it. Unknown domains fall back to the geopolitics recipe with their own label.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import base

GEOPOLITICS = "geopolitics"


@dataclass(frozen=True)
class Domain:
    id: str
    label: str
    loaders: Callable[[], dict[str, base.Loader]]
    uses_radar: bool = True
    sweep: bool = True            # the daily's region-grouped "Around the world" digest (built for countries and the geopolitics library)
    topics: tuple[tuple[str, str], ...] = field(default_factory=tuple)      # (area, what to watch for in it)
    scope: str = ""                                                          # one paragraph telling the clusterer what this board is

    def note(self) -> str:
        """The domain paragraph appended to the clustering role ('' for geopolitics, whose role text is the default)."""
        if not self.topics:
            return ""
        areas = "\n".join(f"- {name}: {watch}" for name, watch in self.topics)
        return (f"\nTHIS BOARD IS THE {self.label.upper()} DESK'S. {self.scope}\n"
                f"Standing topic areas, as lenses (a topic with no persistent dynamic in the headlines yields no theater, and one dynamic may span two):\n"
                f"{areas}\nSet `domain` to `{self.id}` for every theater on this board. Headlines come from source classes tagged on each line "
                f"(ai_sources = labs, research and policy shops, trade press; ai_community = what practitioners are discussing, with points).\n")


def _geopolitics_loaders() -> dict[str, base.Loader]:
    return base.default_loaders()


def _ai_loaders() -> dict[str, base.Loader]:
    return {base.AI_SOURCES: base.ai_library_heads, base.AI_COMMUNITY: base.ai_community_heads}


GEO = Domain(GEOPOLITICS, "Geopolitics", _geopolitics_loaders)

AI = Domain(
    "ai", "Artificial intelligence", _ai_loaders, uses_radar=False, sweep=False,
    scope="It follows the technology, the firms and institutions building it, and the states and markets reacting to it, as ongoing contests between "
          "actors: not product reviews and not one-off launches unless they move a contest.",
    topics=(
        ("Frontier labs race", "model releases, capability and benchmark jumps, who is ahead and the strategy and rivalries behind it"),
        ("Compute, chips and supply", "accelerators, fabs, data-centre and power build-out, export controls and the supply chains behind them"),
        ("Policy, regulation and law", "legislation, standards, court cases (copyright, liability), regulator actions, international agreements"),
        ("AI in security and the military", "cyber offence and defence, military and intelligence use, autonomous systems, misuse and abuse"),
        ("Open-weights ecosystem", "open model releases and licences, the open versus closed gap, the community and the China-US open race"),
        ("AI economics and capital", "capex, funding and valuations, pricing wars, revenue, adoption and labour-market effects"),
        ("Safety, alignment and evaluation", "incidents, evaluations, lab safety commitments, interpretability and control research, the safety debate"),
    ))

REGISTRY: dict[str, Domain] = {d.id: d for d in (GEO, AI)}


def get(domain: str) -> Domain:
    """The domain's recipe data; an unknown id gets the geopolitics recipe under its own name."""
    d = (domain or GEOPOLITICS).strip().lower()
    return REGISTRY.get(d) or Domain(d, d.title(), _geopolitics_loaders)


def owns(domain: str, entry_domain: str) -> bool:
    """Does the registry entry (a theater's stored free-word domain) belong on ``domain``'s board? Geopolitics keeps every legacy label
    (politics, economics, technology ...) except those another registered domain has claimed."""
    mine = (domain or GEOPOLITICS).lower()
    theirs = (entry_domain or GEOPOLITICS).lower()
    if mine == GEOPOLITICS:
        return theirs not in {k for k in REGISTRY if k != GEOPOLITICS}
    return theirs == mine


def boards_dir(store: Path, domain: str) -> Path:
    """Where a domain's heat boards live: the historical ``boards/`` for geopolitics, ``boards/<domain>/`` for the others."""
    d = (domain or GEOPOLITICS).lower()
    return store / "boards" if d == GEOPOLITICS else store / "boards" / d
