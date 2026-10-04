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
#: ``(feed id, url, pillar, channel)``. The fourth field is the **menu channel**, and it
#: exists because this registry outgrew its name. It began as science-only; it now carries AI,
#: world and regional news too, and filing a Nikkei Asia markets story under a channel called
#: "science" would be actively misleading to whoever reads the menu. The pillar is the topic;
#: the channel is where it appears. Each channel is capped separately, so a large group cannot
#: crowd out a small one — which is exactly how AI got squeezed out before.
FEEDS: tuple[tuple[str, str, str, str], ...] = (
    # ── Science ─────────────────────────────────────────────────────────────────────
    ("nature", "https://www.nature.com/nature.rss", "science", "science"),
    ("phys_org", "https://phys.org/rss-feed/", "science", "science"),
    ("science_daily", "https://www.sciencedaily.com/rss/top/science.xml", "science", "science"),
    ("esa", "https://www.esa.int/rssfeed/Our_Activities/Space_Science", "science", "science"),
    ("quanta", "https://api.quantamagazine.org/feed/", "science", "science"),
    ("science_news", "https://www.sciencenews.org/feed", "science", "science"),
    ("new_scientist", "https://www.newscientist.com/section/news/feed/", "science", "science"),
    ("eos", "https://eos.org/feed", "science", "science"),
    ("live_science", "https://www.livescience.com/feeds/all", "science", "science"),
    ("smithsonian", "https://www.smithsonianmag.com/rss/science-nature/", "science", "science"),
    ("nasa", "https://www.nasa.gov/news-release/feed/", "science", "science"),
    ("ars_science", "https://feeds.arstechnica.com/arstechnica/science", "science", "science"),
    ("spacenews", "https://spacenews.com/feed/", "science", "science"),
    # Engineering feats and megaprojects — the "how did they build that" register. Added
    # because the menu had no home for the class of story an operator kept seeing elsewhere
    # (a 582-tonne fusion magnet, a domestic lithography tool) and we never surfaced.
    ("interesting_eng", "https://interestingengineering.com/rss", "science", "science"),

    # ── AI and computing ────────────────────────────────────────────────────────────
    # Added because AI was structurally absent from the menu, and the arithmetic shows why:
    # the beat registry holds 41 slices, refreshes 8 per run, and drops anything not
    # refreshed within 24h — so at one or two runs a day roughly 33 beats contribute
    # nothing, and `pillar:ai` only appears if it wins that lottery AND survives the DOC
    # throttle. On the last live run it was drawn and came back `rate_limited`. Routing AI
    # through feeds instead removes both failure modes at once: free, unthrottled, and
    # edited by people. The same reasoning that created this channel for science.
    ("ars_tech", "https://feeds.arstechnica.com/arstechnica/technology-lab", "ai", "ai"),
    ("wired_ai", "https://www.wired.com/feed/tag/ai/latest/rss", "ai", "ai"),
    ("mit_tr_ai", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "ai", "ai"),
    ("verge_ai", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "ai", "ai"),
    ("techcrunch_ai", "https://techcrunch.com/category/artificial-intelligence/feed/", "ai", "ai"),
    ("hf_blog", "https://huggingface.co/blog/feed.xml", "ai", "ai"),
    ("deepmind", "https://deepmind.google/blog/rss.xml", "ai", "ai"),
    ("openai_news", "https://openai.com/news/rss.xml", "ai", "ai"),
    ("import_ai", "https://importai.substack.com/feed", "ai", "ai"),

    # ── Health, climate ─────────────────────────────────────────────────────────────
    ("statnews", "https://www.statnews.com/feed/", "health", "science"),
    ("nature_medicine", "https://www.nature.com/nm.rss", "health", "science"),
    ("carbon_brief", "https://www.carbonbrief.org/feed/", "environment", "science"),
    ("grist", "https://grist.org/feed/", "environment", "science"),

    # ── World, reported from outside the Anglo-American press ───────────────────────
    # The gap this closes: GKG and the beat sweep both read the same global wire corpus, so
    # discovery inherited whichever stories that corpus amplifies. These are edited desks in
    # other countries with different news judgment — the point is not more volume but a
    # different sense of what leads. Verified live: SCMP led on a Japan quake, MercoPress on
    # a Brazil-Paraguay dispute, Rest of World on Chinese students using AI to pick colleges.
    ("scmp", "https://www.scmp.com/rss/91/feed", "geopolitics", "world"),
    ("nikkei_asia", "https://asia.nikkei.com/rss/feed/nar", "economics", "world"),
    ("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml", "geopolitics", "world"),
    ("dw_world", "https://rss.dw.com/rdf/rss-en-world", "geopolitics", "world"),
    ("france24", "https://www.france24.com/en/rss", "geopolitics", "world"),
    ("thehindu", "https://www.thehindu.com/news/international/feeder/default.rss",
     "geopolitics", "world"),
    ("restofworld", "https://restofworld.org/feed/latest/", "technology", "world"),
    ("japan_times", "https://www.japantimes.co.jp/feed/", "geopolitics", "world"),
    ("africanews", "https://www.africanews.com/feed/rss", "geopolitics", "world"),
    ("mercopress", "https://en.mercopress.com/rss/", "geopolitics", "world"),
    ("defense_one", "https://www.defenseone.com/rss/all/", "defense", "world"),
)

# Verified live before being wired in, which caught two that looked right and were not:
# Ars Technica's ``information-technology`` path 404s (the feed is ``technology-lab``), and
# Inside Climate News returns 403 to our user agent. A feed is only useful if it actually
# parses, so each addition is checked rather than assumed.
#
# Note the archive-shaped feeds — OpenAI (~1,055 entries), Hugging Face (~833), DeepMind
# (~100) publish their whole history in one document. We take the top ``per_feed``, which is
# correct only while they stay newest-first; they do today. If one ever reorders, that feed
# quietly starts serving old posts rather than failing loudly, which is the failure mode to
# watch for here.

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
    feeds: tuple[tuple[str, ...], ...] | None = None,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """Pull recent items from each science feed. One bad feed never sinks the rest."""
    import httpx

    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS, follow_redirects=True)
    hits: list[dict[str, Any]] = []
    try:
        for row in (feeds or FEEDS):
            # Rows are (id, url, pillar, channel); a three-field row is accepted and defaults
            # to the science channel, so callers and fixtures predating the split still work.
            feed_id, url, pillar = row[0], row[1], row[2]
            channel = row[3] if len(row) > 3 else "science"
            try:
                response = http.get(url)  # type: ignore[attr-defined]
                if getattr(response, "status_code", 0) != 200:
                    continue
                entries = parse_feed(response.content)
            except Exception:  # noqa: BLE001 — a dead feed is one fewer source, not an error
                continue
            kept = [e for e in entries if not is_feed_boilerplate(e["title"])]
            for entry in kept[:per_feed]:
                hits.append({**entry, "feed": feed_id, "pillar": pillar, "group": channel})
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
