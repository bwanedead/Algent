"""
Corpus memory — what the newsroom already knows, retrieved for the work in front of it.

The profile store only ever accumulated: every research run started from zero and re-derived what an
earlier run had already graded. ``related`` is the read path. Given the text of a new job (a research
vector, a theater) it ranks prior profiles, then picks the most useful CLAIMS from them, under a
character budget, as a ``CorpusContext`` the caller hands to a researcher or writer.

Plain Python, local and fast. No embeddings: the corpus is hundreds of profiles, and three cheap
signals that mean different things beat one opaque similarity score.

RANKING (per profile; every signal is a 0..1 coverage so the weights are comparable):

  relevance = (0.4 * entities + 0.3 * sources + 0.3 * wording) * recency

* entities - the graph join-key. Shared people/orgs/places/events say "same actors" even when the
  words differ. Entities named in ``entities`` plus any profile entity whose name appears in
  ``query_text``. Rare entities count for more (idf): "United States" links everything, so it links
  nothing; a named minister links a lot. Coverage = matched idf / idf of the query's known entities.
* sources - shared evidence. The same URL is the strongest link there is; the same publisher domain is
  a weak one (idf-weighted, at a quarter of a URL), so a wire everyone cites does not drown the rest.
* wording - BM25 over title + summary + claim texts. Catches topical neighbours that share no entity or
  source yet. Normalised by the best match in this query, so it ranks and never gates.
* recency - a multiplier that decays from 1 toward a floor (0.6) with a half-life of 240 days. Old
  knowledge is discounted, never discarded: a stable confirmed fact from last year is still the best
  footing there is. Undated profiles get the midpoint.

Nothing is cut by a relevance threshold. A profile must show at least one signal; after that the
ranking and the character budget decide what the researcher sees.

CLAIM SELECTION (from the top profiles): score = profile relevance * (0.25 + claim relevance) * grade
* salience * grounding * dated. Confirmed beats likely beats contested beats unconfirmed; high salience
beats low; a claim backed by a page we read beats a snippet; a claim with its own date beats one that
only inherits its profile's. Claims are taken best-first until the budget is spent, with a per-profile
cap so one big profile cannot be the only voice. Output order is deterministic (profile rank, then
claim score, then id).

The index is built lazily from the store and cached per (store dir, file count, newest mtime); a new
profile invalidates it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Iterable
from urllib.parse import urlparse

from .assembly import _norm_url
from .profile import Claim, SignalProfile

# ── knobs (documented in the module docstring) ──────────────────────────────────────────────────
W_ENTITY, W_SOURCE, W_LEXICAL = 0.4, 0.3, 0.3
DOMAIN_WEIGHT = 0.25
RECENCY_FLOOR, RECENCY_HALF_LIFE_DAYS = 0.6, 240.0
BM25_K1, BM25_B = 1.5, 0.75
DEFAULT_BUDGET_CHARS = 6000
DEFAULT_PROFILE_LIMIT = 8
MAX_CLAIMS_PER_PROFILE = 6
MAX_CLAIM_CHARS = 400

_GRADE = {"confirmed": 1.0, "likely": 0.8, "contested": 0.5, "unconfirmed": 0.35, "speculative": 0.2,
          "opinion": 0.15}
_SALIENCE = {"high": 1.0, "medium": 0.7, "low": 0.4}
_GROUNDING = {"snapshotted": 1.0, "snippet_only": 0.85, "unsourced": 0.6}
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")
_TOKEN = re.compile(r"[a-z0-9]{3,}")


# ── result types ────────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RelatedProfile:
    id: str
    title: str
    date: str
    reasons: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class RelatedClaim:
    claim_id: str
    profile_id: str
    text: str
    grade: str
    date: str
    date_basis: str            # source | learned | profile  (how the date was found)
    sources: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class CorpusContext:
    """What the corpus offered for one job. ``profiles`` are the graph edges; ``claims`` the facts."""

    profiles: tuple[RelatedProfile, ...] = ()
    claims: tuple[RelatedClaim, ...] = ()

    @property
    def empty(self) -> bool:
        return not self.claims

    @property
    def profile_ids(self) -> list[str]:
        return [p.id for p in self.profiles]

    @property
    def claim_ids(self) -> set[str]:
        return {c.claim_id for c in self.claims}

    @property
    def source_urls(self) -> set[str]:
        return {u for c in self.claims for u in c.sources}

    def summaries(self, width: int = 160) -> list[str]:
        """One line per claim for the new profile's ``corpus_context`` (what we already knew)."""
        return [f"{c.claim_id} [{c.grade}] {c.text[:width]} ({c.date}) <- {c.profile_id}" for c in self.claims]

    def render(self) -> str:
        """The claims grouped under the profile they came from, ids and dates visible."""
        by_profile: dict[str, list[RelatedClaim]] = {}
        for c in self.claims:
            by_profile.setdefault(c.profile_id, []).append(c)
        out: list[str] = []
        for p in self.profiles:
            if p.id not in by_profile:
                continue
            out.append(f"## {p.title} (profile {p.id}, {p.date or 'undated'}; related by {'; '.join(p.reasons)})")
            out += [_claim_line(c) for c in by_profile[p.id]]
        return "\n".join(out)

    def to_dict(self) -> dict[str, Any]:
        return {"profiles": [p.__dict__ | {"reasons": list(p.reasons)} for p in self.profiles],
                "claims": [c.__dict__ | {"sources": list(c.sources)} for c in self.claims]}


def _claim_line(c: RelatedClaim) -> str:
    src = f" [sources: {', '.join(c.sources[:3])}]" if c.sources else ""
    return f"- [{c.claim_id}] ({c.grade}, {c.date}) {c.text}{src}"


# ── index ───────────────────────────────────────────────────────────────────────────────────────
def _words(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def _key(name: str) -> str:
    """Normalised entity name: lowercase alphanumerics, single spaces ('Strait of  Hormuz.' -> same key)."""
    return " ".join(re.findall(r"[a-z0-9]+", (name or "").lower()))


def _domain(url: str) -> str:
    return urlparse(url if "//" in url else f"//{url}").netloc.lower().removeprefix("www.")


def _day(text: str) -> date | None:
    m = _ISO_DAY.match((text or "").strip())
    try:
        return date.fromisoformat(m.group(0)) if m else None
    except ValueError:
        return None


def _profile_date(p: SignalProfile) -> str:
    d = _day(p.as_of) or _day(p.generated_at)
    return d.isoformat() if d else ""


@dataclass(frozen=True)
class _Doc:
    profile: SignalProfile
    date: str
    entity_names: dict[str, str]          # key -> display name
    urls: frozenset[str]
    domains: frozenset[str]
    tf: Counter
    length: int


class _Index:
    def __init__(self, profiles: Iterable[SignalProfile]) -> None:
        self.docs: list[_Doc] = []
        self.ent_df: Counter = Counter()
        self.url_df: Counter = Counter()
        self.dom_df: Counter = Counter()
        self.tok_df: Counter = Counter()
        for p in sorted(profiles, key=lambda p: p.id):
            names: dict[str, str] = {}
            for e in p.entities:
                for n in (e.canonical_name, e.name, *e.aliases):
                    if len(_key(n)) >= 3:
                        names.setdefault(_key(n), n)
            urls = frozenset(_norm_url(s.url) for s in p.source_ledger if s.url)
            doms = frozenset(d for d in (_domain(u) for u in urls) if d)
            text = " ".join([p.title, p.summary, *(c.text for c in p.claim_ledger)])
            tf = Counter(_words(text))
            self.docs.append(_Doc(p, _profile_date(p), names, urls, doms, tf, sum(tf.values())))
            self.ent_df.update(names.keys())
            self.url_df.update(urls)
            self.dom_df.update(doms)
            self.tok_df.update(tf.keys())
        self.n = len(self.docs)
        self.avgdl = (sum(d.length for d in self.docs) / self.n) if self.n else 1.0

    def idf(self, df: int) -> float:
        return math.log(1 + self.n / df) if df else 0.0

    def bm25_idf(self, token: str) -> float:
        df = self.tok_df.get(token, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5)) if df else 0.0


_CACHE: dict[str, tuple[Any, _Index]] = {}


def _load(store: Any) -> list[SignalProfile]:
    it = getattr(store, "iter_profiles", None)
    if it is not None:
        return list(it())
    return [p for p in (store.get(i) for i in store.list_ids()) if p is not None]


def _index_for(store: Any) -> _Index:
    root = getattr(store, "root", None)
    sig = None
    if root is not None and root.exists():
        stats = [f.stat().st_mtime_ns for f in root.glob("*.json")]
        sig = (len(stats), max(stats, default=0))
    hit = _CACHE.get(str(root)) if sig is not None else None
    if hit is not None and hit[0] == sig:
        return hit[1]
    index = _Index(_load(store))
    if sig is not None:
        _CACHE[str(root)] = (sig, index)
    return index


# ── retrieval ───────────────────────────────────────────────────────────────────────────────────
def related(store: Any, *, query_text: str, entities: Iterable[str] = (), sources: Iterable[str] = (),
            exclude_ids: Iterable[str] = (), as_of: str | None = None, older_than: str | None = None,
            limit: int = DEFAULT_PROFILE_LIMIT, budget_chars: int = DEFAULT_BUDGET_CHARS) -> CorpusContext:
    """Prior knowledge relevant to ``query_text`` (+ known ``entities`` / ``sources``).

    ``exclude_ids`` skips profiles (the one being built or enriched). ``as_of`` (YYYY-MM-DD) hides
    anything dated after it, so a replay sees only what was known then. ``older_than`` keeps only
    claims dated before it, for callers that already hold the recent evidence. ``limit`` caps the
    profiles consulted; ``budget_chars`` caps the rendered claims. Deterministic for a given store."""
    index = _index_for(store)
    excluded = set(exclude_ids)
    q_norm = f" {_key(query_text)} "
    q_ents = {_key(e) for e in entities if len(_key(e)) >= 3}
    q_ents |= {k for k in index.ent_df if f" {k} " in q_norm}
    q_ents = {k for k in q_ents if index.ent_df.get(k)}
    q_urls = {_norm_url(u) for u in sources if u}
    q_urls = {u for u in q_urls if index.url_df.get(u)}
    q_doms = {d for d in (_domain(u) for u in map(_norm_url, (s for s in sources if s))) if index.dom_df.get(d)}
    q_toks = {t for t in set(_words(query_text)) if index.tok_df.get(t)}

    ent_den = sum(index.idf(index.ent_df[k]) for k in q_ents)
    src_den = (sum(index.idf(index.url_df[u]) for u in q_urls)
               + DOMAIN_WEIGHT * sum(index.idf(index.dom_df[d]) for d in q_doms))
    lexical = {id(d): _bm25(index, d, q_toks) for d in index.docs} if q_toks else {}
    best_lex = max(lexical.values(), default=0.0) or 1.0
    today = _day(as_of) if as_of else None
    now = today or datetime.now(UTC).date()

    ranked: list[tuple[float, _Doc, tuple[str, ...]]] = []
    for d in index.docs:
        if d.profile.id in excluded or (today and d.date and _day(d.date) > today):
            continue
        m_ents = sorted(k for k in q_ents if k in d.entity_names)
        m_urls = [u for u in q_urls if u in d.urls]
        m_doms = sorted(x for x in q_doms if x in d.domains and not any(_domain(u) == x for u in m_urls))
        ent = sum(index.idf(index.ent_df[k]) for k in m_ents) / ent_den if ent_den else 0.0
        src = ((sum(index.idf(index.url_df[u]) for u in m_urls)
                + DOMAIN_WEIGHT * sum(index.idf(index.dom_df[x]) for x in q_doms if x in d.domains)) / src_den
               if src_den else 0.0)
        lex = lexical.get(id(d), 0.0) / best_lex
        if not (ent or src or lex):
            continue
        reasons = []
        if m_ents:
            reasons.append("entities: " + ", ".join(d.entity_names[k] for k in m_ents[:4]))
        if m_urls:
            reasons.append(f"{len(m_urls)} shared source(s)")
        if m_doms:
            reasons.append("same publishers: " + ", ".join(m_doms[:3]))
        if lex:
            reasons.append(f"wording {lex:.2f}")
        score = (W_ENTITY * ent + W_SOURCE * src + W_LEXICAL * lex) * _recency(d.date, now)
        ranked.append((score, d, tuple(reasons)))
    ranked.sort(key=lambda r: (-r[0], r[1].date and -_day(r[1].date).toordinal() or 0, r[1].profile.id))
    top = ranked[:max(limit, 0)]
    profiles = tuple(RelatedProfile(d.profile.id, d.profile.title, d.date, why, round(s, 4)) for s, d, why in top)
    claims = _pick_claims(index, top, q_toks, q_ents, today=today, older_than=older_than, budget=budget_chars)
    return CorpusContext(profiles=profiles, claims=claims)


def _bm25(index: _Index, doc: _Doc, q_toks: set[str]) -> float:
    norm = BM25_K1 * (1 - BM25_B + BM25_B * doc.length / index.avgdl)
    return sum(index.bm25_idf(t) * doc.tf[t] * (BM25_K1 + 1) / (doc.tf[t] + norm) for t in q_toks if doc.tf.get(t))


def _recency(profile_date: str, now: date) -> float:
    d = _day(profile_date)
    if d is None:
        return (1 + RECENCY_FLOOR) / 2
    age = max((now - d).days, 0)
    return RECENCY_FLOOR + (1 - RECENCY_FLOOR) * 0.5 ** (age / RECENCY_HALF_LIFE_DAYS)


def _claim_date(claim: Claim, sources: dict[str, Any], profile_date: str) -> tuple[str, str]:
    """The best date for a claim and how it was found: a supporting source's publication date (when the
    thing was said), else when we learned it, else the profile's own date."""
    pub = [d for d in (_day(sources[s].published_at) for s in claim.supported_by if s in sources) if d]
    if pub:
        return max(pub).isoformat(), "source"
    learned = _day(claim.provenance.created_at) if claim.provenance else None
    if learned:
        return learned.isoformat(), "learned"
    return profile_date, "profile"


def _pick_claims(index: _Index, top: list, q_toks: set[str], q_ents: set[str], *, today: date | None,
                 older_than: str | None, budget: int) -> tuple[RelatedClaim, ...]:
    tok_den = sum(index.bm25_idf(t) for t in q_toks) or 1.0
    per_profile: dict[str, list[RelatedClaim]] = {}
    for rank, (pscore, d, _why) in enumerate(top):
        sources = {s.id: s for s in d.profile.source_ledger}
        found = []
        for c in d.profile.claim_ledger:
            text = " ".join((c.text or "").split())
            if not text:
                continue
            when, basis = _claim_date(c, sources, d.date)
            if (older_than and when and when >= older_than) or (today and when and _day(when) > today):
                continue
            words = set(_words(text))
            rel = min(1.0, sum(index.bm25_idf(t) for t in q_toks if t in words) / tok_den
                      + (0.5 if any(f" {k} " in f" {_key(text)} " for k in q_ents) else 0.0))
            score = (pscore * (0.25 + rel) * _GRADE.get(c.status, 0.35) * _SALIENCE.get(c.salience, 0.7)
                     * _GROUNDING.get(c.grounding, 0.6) * (1.0 if basis == "source" else 0.9 if when else 0.8))
            urls = tuple(dict.fromkeys(sources[s].url for s in c.supported_by if s in sources and sources[s].url))
            found.append(RelatedClaim(c.id, d.profile.id, text[:MAX_CLAIM_CHARS], c.status, when, basis, urls,
                                      round(score, 5)))
        found.sort(key=lambda r: (-r.score, r.claim_id))
        per_profile[d.profile.id] = found[:MAX_CLAIMS_PER_PROFILE]

    # Best-first across profiles until the budget is spent (a profile's header is paid for once).
    order = {d.profile.id: rank for rank, (_s, d, _w) in enumerate(top)}
    titles = {d.profile.id: len(d.profile.title) + 80 for _s, d, _w in top}
    pool = sorted((c for cs in per_profile.values() for c in cs), key=lambda c: (-c.score, c.profile_id, c.claim_id))
    chosen: list[RelatedClaim] = []
    headed: set[str] = set()
    spent = 0
    for c in pool:
        cost = len(_claim_line(c)) + 1 + (0 if c.profile_id in headed else titles[c.profile_id])
        if spent + cost > budget:
            continue
        spent += cost
        headed.add(c.profile_id)
        chosen.append(c)
    chosen.sort(key=lambda c: (order[c.profile_id], -c.score, c.claim_id))
    return tuple(chosen)
