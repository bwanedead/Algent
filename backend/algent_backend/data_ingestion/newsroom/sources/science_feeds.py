"""
Science feeds — the curiosity channel, and the one that doesn't run through GDELT.

Discovery had a structural blind spot: every one of the ~40 registry queries went
through the single GDELT DOC endpoint, so one throttle took out science, AI and every
country at once. ``pillar:science`` had literally never executed — not degraded, never
once — and no ordering scheme downstream can surface astronomy from a pool that has
none in it. This channel removes the chokepoint rather than working around it: a
handful of independent hosts, each free, none needing a key.

It is also deliberately *curated news*, not raw preprints. A journal firehose is
hundreds of papers a day of which a handful are stories, and picking those needs
judgment we don't have at this layer. The feeds below are edited — the selection work
is already done, by people, upstream of us. (arXiv is a reasonable later addition for
grounding a specific claim in the primary source; it is not a discovery channel.)

Parsing covers the three shapes these feeds actually ship: RSS 2.0, RSS 1.0/RDF
(Nature), and Atom. Verified live before being wired in; a feed that changes shape
degrades to zero hits for that feed and never breaks the channel.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

SOURCE_ID = "science_feeds"

_TIMEOUT_S = 20.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery ingestion)"}

_NS = {
    "rss1": "http://purl.org/rss/1.0/",
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# (feed id, url, pillar). All edited by people, which is the point — the selection work is
# already done upstream of us.
#
# Widened from five to twelve because five was not enough for *freshness*: each outlet's top
# items barely move inside a day, so the science menu read as "the same as yesterday" even
# though nothing was broken. Independent editors disagree about what leads, so more outlets
# buys more genuinely different material than drawing deeper from the same few — verified
# live, the added feeds led with Io's interior heat, a NASA deep-space antenna at risk, an
# ancient Mount Rainier mudflow and a Starship recovery attempt, none of which the original
# five carried.
FEEDS: tuple[tuple[str, str, str], ...] = (
    ("nature", "https://www.nature.com/nature.rss", "science"),
    ("phys_org", "https://phys.org/rss-feed/", "science"),
    ("science_daily", "https://www.sciencedaily.com/rss/top/science.xml", "science"),
    ("esa", "https://www.esa.int/rssfeed/Our_Activities/Space_Science", "science"),
    ("quanta", "https://api.quantamagazine.org/feed/", "science"),
    ("science_news", "https://www.sciencenews.org/feed", "science"),
    ("new_scientist", "https://www.newscientist.com/section/news/feed/", "science"),
    ("eos", "https://eos.org/feed", "science"),
    ("live_science", "https://www.livescience.com/feeds/all", "science"),
    ("smithsonian", "https://www.smithsonianmag.com/rss/science-nature/", "science"),
    ("nasa", "https://www.nasa.gov/news-release/feed/", "science"),
    ("ars_science", "https://feeds.arstechnica.com/arstechnica/science", "science"),
)

# Deliberately NOT here: arXiv. Its Atom API works and returns the newest preprints in a
# category, but they are papers rather than stories — a live sample led with
# "Magnetohydrodynamical opening of dust traps in protoplanetary disks". Deciding which of
# several hundred daily preprints is news needs judgment this layer does not have, and adding
# them would fill the menu with titles nothing would ever pick. arXiv is the right place to
# GROUND a specific claim in the primary paper, which is a research-stage job, not a
# discovery channel.


# Feed furniture, not stories: journal metadata and the outlet's own promos. Kept here
# rather than in the shared denylist because it is specific to how these feeds publish.
_BOILERPLATE = (
    "author correction", "publisher correction", "retraction note", "editorial expression",
    "podcast series", "replay of", "media briefing", "call for papers", "news in brief",
)


def is_feed_boilerplate(title: str) -> bool:
    lowered = title.casefold()
    return any(marker in lowered for marker in _BOILERPLATE)


def fetch_science(
    *,
    per_feed: int = 8,
    feeds: tuple[tuple[str, str, str], ...] | None = None,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """Pull recent items from each science feed. One bad feed never sinks the rest."""
    import httpx

    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS, follow_redirects=True)
    hits: list[dict[str, Any]] = []
    try:
        for feed_id, url, pillar in (feeds or FEEDS):
            try:
                response = http.get(url)  # type: ignore[attr-defined]
                if getattr(response, "status_code", 0) != 200:
                    continue
                entries = parse_feed(response.content)
            except Exception:  # noqa: BLE001 — a dead feed is one fewer source, not an error
                continue
            kept = [e for e in entries if not is_feed_boilerplate(e["title"])]
            for entry in kept[:per_feed]:
                hits.append({**entry, "feed": feed_id, "pillar": pillar})
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]
    return hits


def parse_feed(payload: bytes) -> list[dict[str, str]]:
    """``(title, url)`` pairs from an RSS 2.0, RSS 1.0/RDF, or Atom document."""
    root = ET.fromstring(payload)
    for finder, reader in (
        (".//item", _rss2_entry),                    # RSS 2.0
        (".//rss1:item", _rss1_entry),               # RSS 1.0 / RDF (Nature, arXiv)
        (".//atom:entry", _atom_entry),              # Atom
    ):
        nodes = root.findall(finder, _NS) if ":" in finder else root.findall(finder)
        entries = [e for e in (reader(n) for n in nodes) if e]
        if entries:
            return entries
    return []


def _rss2_entry(node: ET.Element) -> dict[str, str] | None:
    return _entry(_text(node, "title"), node.findtext("link"), node.findtext("pubDate"))


def _rss1_entry(node: ET.Element) -> dict[str, str] | None:
    return _entry(
        _text(node, "rss1:title"),
        node.findtext("rss1:link", namespaces=_NS),
        node.findtext("dc:date", namespaces=_NS),
    )


def _atom_entry(node: ET.Element) -> dict[str, str] | None:
    link = node.find("atom:link", _NS)
    href = link.get("href") if link is not None else None
    return _entry(
        _text(node, "atom:title"),
        href,
        node.findtext("atom:updated", namespaces=_NS),
    )


def _text(node: ET.Element, path: str) -> str:
    """All of a child's text, including any inline markup's.

    ``findtext`` stops at the first child element, so a title carrying real markup —
    Nature italicises species names — arrived as "Baby" instead of "Baby T. rex were
    killers from birth". Feeds ship that markup both ways (parsed children when it is
    literal, escaped text when it is entity-encoded), so gather the children here and
    let ``_clean`` handle the escaped case.
    """
    child = node.find(path, _NS) if ":" in path else node.find(path)
    return "".join(child.itertext()) if child is not None else ""


def _entry(title: str | None, url: str | None, when: str | None) -> dict[str, str] | None:
    title = _clean(title)
    url = (url or "").strip()
    if not title or not url:
        return None
    return {
        "title": title,
        "url": url,
        "domain": url.split("/")[2] if "://" in url else "",
        "seendate": (when or "").strip(),
    }


def _clean(title: str | None) -> str:
    """Feed titles carry inline markup (Nature italicises species names)."""
    if not title:
        return ""
    out, depth = [], 0
    for char in title:
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return " ".join("".join(out).split())
