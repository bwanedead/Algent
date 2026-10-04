"""
Search the library: FTS5/BM25 relevance, bent by recency and by how primary the source is.

    score = relevance * kind_weight * recency

- ``relevance``: FTS5 ``bm25`` (title weighted 5x text), sign-flipped so bigger is better. It is the only
  term that depends on the query, which is why the other two are multipliers: they re-order near-equal
  matches without letting a fresh press release outrank a page that actually answers the question.
- ``kind_weight`` (``KIND_WEIGHT``): government / ministry / international org / central bank / statistics
  office 1.5, think tank / research / NGO 1.2, wire and regional news 1.0. On equal relevance the primary
  record wins; a clearly better-matching news page still beats a weak primary one.
- ``recency``: ``0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)``, floored at ``RECENCY_FLOOR`` so an old
  primary document stays findable rather than vanishing. Age is the published date (fetch date if the
  feed gave none).

No hard gates: nothing is dropped for being old or low-weight (use ``days`` / ``kinds`` to ask for that).
BM25 candidates (``CANDIDATES`` best) are re-ranked in Python. Query: words are AND-ed; if that finds
fewer than ``limit``, pages matching only some of the words top the list up (listed after the all-words matches). "double quotes" keep a phrase; ``site:host`` restricts to a domain.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from . import store
from .sources import ANALYSIS_KINDS, PRIMARY_KINDS

KIND_WEIGHT = {**{k: 1.5 for k in PRIMARY_KINDS}, **{k: 1.2 for k in ANALYSIS_KINDS}}
DEFAULT_KIND_WEIGHT = 1.0
RECENCY_HALF_LIFE_DAYS = 30.0
RECENCY_FLOOR = 0.3
CANDIDATES = 100
TITLE_WEIGHT, TEXT_WEIGHT = 5.0, 1.0

_TERM = re.compile(r'"([^"]+)"|(\S+)')
_SITE = re.compile(r"(?:^|\s)site:(\S+)", re.I)
_WORD = re.compile(r"\w+", re.UNICODE)


def _parse_query(query: str) -> tuple[list[str], str]:
    """(FTS terms, site filter). A term is a quoted phrase or a single word; punctuation is dropped."""
    site = ""
    m = _SITE.search(query)
    if m:
        site = m.group(1).lower().lstrip(".")
        query = _SITE.sub(" ", query)
    terms = []
    for phrase, word in _TERM.findall(query):
        words = _WORD.findall(phrase or word)
        if len(words) > 1 and phrase:
            terms.append('"' + " ".join(words) + '"')
        elif words:
            terms.extend(f'"{w}"' for w in words)
    return terms, site


def recency_factor(published_or_fetched: str, now: datetime) -> float:
    try:
        when = datetime.fromisoformat(published_or_fetched)
    except ValueError:
        return RECENCY_FLOOR
    age_days = max(0.0, (now - (when if when.tzinfo else when.replace(tzinfo=UTC))).total_seconds() / 86400)
    return max(RECENCY_FLOOR, 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS))


def _run(conn: Any, match: str, site: str, cutoff: str, kinds: list[str] | None) -> list[Any]:
    where, args = ["docs_fts MATCH ?"], [match]
    if cutoff:
        where.append("COALESCE(NULLIF(d.published,''), d.fetched_at) >= ?")
        args.append(cutoff)
    if kinds:
        where.append(f"d.kind IN ({','.join('?' * len(kinds))})")
        args.extend(kinds)
    if site:
        where.append("(d.domain = ? OR d.domain LIKE ?)")
        args.extend([site, f"%.{site}"])
    sql = (f"SELECT d.url, d.title, d.source_id, d.kind, d.domain, d.published, d.fetched_at,"  # noqa: S608 - clauses are fixed text
           f" snippet(docs_fts, -1, '', '', ' ... ', 28) AS snip, bm25(docs_fts, {TITLE_WEIGHT}, {TEXT_WEIGHT}) AS bm"
           f" FROM docs_fts JOIN documents d ON d.id = docs_fts.rowid WHERE {' AND '.join(where)}"
           f" ORDER BY bm LIMIT {CANDIDATES}")
    return conn.execute(sql, args).fetchall()


def search(query: str, *, days: int | None = None, kinds: list[str] | None = None, limit: int = 10,
           now: datetime | None = None) -> list[dict[str, Any]]:
    """Ranked hits from the library, or [] when it is empty / absent / the query has no usable words."""
    terms, site = _parse_query(query or "")
    if not terms and not site:
        return []
    conn = store.connect(create=False)
    if conn is None:
        return []
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=days)).isoformat() if days else ""
    try:
        rows, topup = [], []
        if terms:
            rows = _run(conn, " AND ".join(terms), site, cutoff, kinds)
            if len(rows) < limit and len(terms) > 1:     # all-words matches lead; partial matches top up the list
                have = {r["url"] for r in rows}
                topup = [r for r in _run(conn, " OR ".join(terms), site, cutoff, kinds) if r["url"] not in have]
        else:                                            # only site: -> newest pages of that site
            rows = conn.execute(
                "SELECT url, title, source_id, kind, domain, published, fetched_at, substr(text,1,200) AS snip, -1.0 AS bm"
                " FROM documents WHERE latest=1 AND (domain=? OR domain LIKE ?) ORDER BY COALESCE(NULLIF(published,''), fetched_at)"
                " DESC LIMIT ?", (site, f"%.{site}", CANDIDATES)).fetchall()
    finally:
        conn.close()
    return [h for group in (rows, topup) for h in _rank(group, now)][:max(1, limit)]


def _rank(rows: list[Any], now: datetime) -> list[dict[str, Any]]:
    scored = []
    for r in rows:
        score = (-r["bm"]) * KIND_WEIGHT.get(r["kind"], DEFAULT_KIND_WEIGHT) * recency_factor(r["published"] or r["fetched_at"], now)
        scored.append((score, {"title": r["title"], "url": r["url"], "source": r["source_id"], "kind": r["kind"],
                               "published": r["published"], "snippet": " ".join(r["snip"].split())}))
    scored.sort(key=lambda h: h[0], reverse=True)
    return [hit for _, hit in scored]
