"""
Turn a t1 portfolio into themed briefing clusters.

A cluster is one X post: a topic line, then the menu blurbs for that pillar. No
Radar stamp, no effort/hits metadata, no thread. Radar may already have said one
of these — that is fine; a roundup is a different object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from algent_backend.agent_system.agents.newsroom.flags import (
    briefing_max_clusters,
    briefing_max_items,
    briefing_min_items,
)

#: How the topic line is phrased. Underscore pillars become spaces; a few get a
#: readable alias so "today's headlines on world_events" never ships.
_TOPIC = {
    "ai": "AI",
    "world_events": "world events",
}

#: Physical scenes for the collage, kept inside the hero-image subject guards:
#: no quantities, no "map"/"chart"/"data", no more than 14 words. The headline
#: never goes near the image model.
_COLLAGE_SUBJECT = {
    "energy": "high voltage towers, gas flares, and industrial plants at dusk",
    "geopolitics": "cargo ships, border fences, and government buildings under grey sky",
    "economics": "shipping containers, bank facades, and factory gates at dawn",
    "finance": "trading-floor screens, bank facades, and a busy port crane",
    "ai": "server halls, circuit boards, and factory robots under cool light",
    "technology": "circuit boards, radio masts, and a clean factory floor",
    "science": "laboratory glassware, telescopes, and field instruments on a bench",
    "environment": "wildfire smoke, drought-cracked earth, and a hazy river valley",
    "health": "hospital corridors, pharmacy shelves, and instruments on a tray",
    "defense": "naval vessels, radar dishes, and hangars on a distant airfield",
    "world_events": "city squares, ports, and empty highways under overcast light",
    "politics": "capitol steps, empty chambers, and press-room lights",
}
_COLLAGE_DEFAULT = "radio masts, newsprint stacks, and a city skyline at dawn"
_COLLAGE_SETTING = "arranged as one wide editorial collage, distinct scenes sharing the frame"


@dataclass(frozen=True)
class Cluster:
    pillar: str
    vectors: tuple[dict[str, Any], ...]

    @property
    def vector_ids(self) -> tuple[str, ...]:
        return tuple(str(v.get("id") or v.get("title") or "") for v in self.vectors)

    def key(self, t0_ref: str) -> str:
        ids = ",".join(self.vector_ids)
        return f"{t0_ref}:{self.pillar}:{ids}"


def topic_label(pillar: str) -> str:
    key = (pillar or "world").strip() or "world"
    if key in _TOPIC:
        return _TOPIC[key]
    return key.replace("_", " ")


def format_briefing(pillar: str, vectors: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> str:
    """The post body. Header, then one bullet per blurb. No titles-as-headlines."""
    lines = [f"today's headlines on {topic_label(pillar)}:", ""]
    for vector in vectors:
        blurb = " ".join(str(vector.get("thesis") or vector.get("title") or "").split())
        if blurb:
            lines.append(f"• {blurb}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def collage_subject(pillar: str) -> str:
    return _COLLAGE_SUBJECT.get((pillar or "").strip(), _COLLAGE_DEFAULT)


def collage_setting() -> str:
    return _COLLAGE_SETTING


def cluster_portfolio(portfolio: dict[str, Any]) -> list[Cluster]:
    """Group vectors by primary pillar, chunked to the standing min/max."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for vector in portfolio.get("vectors") or []:
        if not isinstance(vector, dict):
            continue
        pillar = str((vector.get("pillars") or ["world"])[0] or "world")
        buckets.setdefault(pillar, []).append(vector)

    min_n = briefing_min_items()
    max_n = briefing_max_items()
    out: list[Cluster] = []
    for pillar, items in buckets.items():
        for chunk in _chunks(items, min_n=min_n, max_n=max_n):
            out.append(Cluster(pillar=pillar, vectors=tuple(chunk)))
    out.sort(key=lambda c: len(c.vectors), reverse=True)
    return out[: briefing_max_clusters()]


def _chunks(items: list[dict[str, Any]], *, min_n: int, max_n: int) -> list[list[dict[str, Any]]]:
    if len(items) < min_n:
        return []
    if len(items) <= max_n:
        return [items]
    groups: list[list[dict[str, Any]]] = []
    rest = list(items)
    while len(rest) > max_n:
        groups.append(rest[:max_n])
        rest = rest[max_n:]
    if len(rest) >= min_n:
        groups.append(rest)
    elif groups and len(groups[-1]) + len(rest) <= max_n:
        groups[-1] = groups[-1] + rest
    return groups
