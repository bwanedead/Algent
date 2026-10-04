"""
arXiv — the primary-literature channel, deliberately kept in its own lane.

Every earlier note in this codebase argued *against* wiring arXiv into discovery, and
that reasoning still holds on its own terms: a preprint firehose is hundreds of papers
a day of which a handful are stories, and titles like "Magnetohydrodynamical opening
of dust traps in protoplanetary disks" are not leads. Judging which preprint is news
needs domain expertise this layer does not have.

It is here anyway, for two reasons that the earlier argument missed.

**It is separate, so it cannot dilute anything.** Papers land on their own ``papers``
channel with its own cap, so they appear as their own block in the menu and can be
skipped wholesale. The cost of having them is bounded to that block; the cost of NOT
having them is that a genuinely important result is invisible to us until a magazine
happens to write it up, days later.

**The research layer wants primary sources.** Doctrine now tells the profile stage to
reconstruct stories from primary artifacts rather than echo a wire report, and for a
science story the primary artifact IS the paper. Having the newest work in a category
already indexed means research can reach for the paper instead of somebody's summary
of it.

So this channel is not trying to be interesting on its own. It is trying to make sure
that when something matters, the primary record is one hop away.
"""

from __future__ import annotations

from typing import Any

SOURCE_ID = "arxiv"

_API = "http://export.arxiv.org/api/query"
_TIMEOUT_S = 25.0
_HEADERS = {"User-Agent": "Algent/0.1 (news discovery ingestion)"}

#: Categories worth watching, grouped so one query covers a domain. Chosen for topics a
#: general reader can be brought to care about — fusion and plasma, astrophysics, quantum
#: computing, climate, genomics, AI — rather than for coverage of the archive.
CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("physics", "cat:physics.plasm-ph OR cat:cond-mat.supr-con OR cat:quant-ph", "science"),
    ("space", "cat:astro-ph.HE OR cat:astro-ph.EP OR cat:astro-ph.GA", "science"),
    ("earth", "cat:physics.ao-ph OR cat:physics.geo-ph", "environment"),
    ("bio", "cat:q-bio.PE OR cat:q-bio.GN", "science"),
    ("ai", "cat:cs.AI OR cat:cs.LG OR cat:cs.CL", "ai"),
)

#: Per category. Small on purpose — this channel is a reference shelf, not a menu.
DEFAULT_PER_CATEGORY = 4


def fetch_arxiv(
    *,
    per_category: int = DEFAULT_PER_CATEGORY,
    categories: tuple[tuple[str, str, str], ...] | None = None,
    client: object | None = None,
) -> list[dict[str, Any]]:
    """Newest submissions per category. One failed query never sinks the rest."""
    import httpx

    from .science_feeds import parse_feed

    own = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S, headers=_HEADERS, follow_redirects=True)
    hits: list[dict[str, Any]] = []
    try:
        for group, query, pillar in (categories or CATEGORIES):
            try:
                response = http.get(_API, params={  # type: ignore[attr-defined]
                    "search_query": query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": max(1, int(per_category)),
                })
                if getattr(response, "status_code", 0) != 200:
                    continue
                entries = parse_feed(response.content)
            except Exception:  # noqa: BLE001 — a failed category is one fewer, not an error
                continue
            for entry in entries[:per_category]:
                hits.append({
                    **entry,
                    "title": _tidy(entry.get("title", "")),
                    "feed": f"arxiv_{group}",
                    "pillar": pillar,
                    # Its own menu channel — papers never mix into the news blocks.
                    "group": "papers",
                })
    finally:
        if own:
            http.close()  # type: ignore[attr-defined]
    return hits


def _tidy(title: str) -> str:
    """arXiv wraps titles across lines and pads them; collapse to one clean line."""
    return " ".join(str(title or "").split())
