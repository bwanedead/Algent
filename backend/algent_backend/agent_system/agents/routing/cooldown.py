"""
Mechanical story-family cooldown — the floor under the soft "don't pick a close match" instruction.

Soft cooldown alone can fail: the model re-titles the same beat as a "material new development"
and promotes it anyway. Headlines are still advisory data for the model; this module is the
**deterministic floor** that keeps a story-family already on the site out of the #1 slot.

A candidate is "cooled" when it shares distinctive tokens with recent headlines (or a token that
has already appeared in two+ recent titles — the saturation signal). Cooled candidates stay in
the ranking (on-deck is fine) but are demoted below every non-cooled choice so they cannot promote.
"""

from __future__ import annotations

import re
from collections import Counter

from .contracts import RouteCandidate, RouteRanking

# Floor: share this many significant tokens with a single prior title → same story family.
_MIN_SHARED = 2
# Or share one longer "anchor" token (places, orgs, products — not generic news verbs).
_ANCHOR_LEN = 6
# A token seen in this many cooldown titles is a saturated beat key.
_SATURATION_COUNT = 2

_TOKEN = re.compile(r"[a-z0-9]+", re.I)
_STOP = frozenset({
    "about", "after", "again", "against", "among", "because", "before", "being", "between",
    "could", "during", "every", "first", "from", "have", "into", "just", "more", "most",
    "near", "only", "other", "over", "same", "should", "since", "some", "still", "such",
    "than", "that", "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "under", "until", "very", "what", "when", "where", "which", "while", "will",
    "with", "would", "your", "says", "said", "amid", "onto", "also", "into", "were", "been",
    "does", "doing", "make", "made", "much", "many", "both", "each", "few", "own", "same",
    "record", "remains", "remain", "despite", "ongoing", "around", "across", "after",
    "sees", "seen", "seem", "seems", "keep", "kept", "come", "came", "take", "took",
    # Generic news glue — never family anchors (would false-match unrelated stories).
    "active", "damage", "severe", "major", "crisis", "attack", "attacks", "struck", "strike",
    "strikes", "warning", "warned", "report", "reports", "official", "officials", "security",
    "military", "forces", "people", "public", "world", "global", "latest", "update", "updates",
    "under", "against", "between", "without", "within", "through", "during", "before",
    "server", "servers", "system", "systems", "support", "edition", "version", "versions",
    "traffic", "reduce", "reduced", "closure", "closed", "open", "opened", "prove", "proves",
    "durable", "sustained", "serious", "heavy", "broad", "enterprise", "campaign", "exploited",
    "exploitation", "patching", "patches", "vulnerability", "vulnerabilities",
    "levels", "level", "higher", "lower", "surge", "push", "data", "show", "shows",
    # Abstract glue that co-occurs across unrelated headlines (live false demotes).
    "concern", "concerns", "whether", "market", "markets", "credit", "stress", "still",
    "unproven", "inflation", "forces", "central", "banks", "heading", "record",
    "toward", "towards", "increasingly", "infrastructure", "risk", "risks",
    "warning", "warned", "warns", "test", "tests", "stays", "headline",
    "shipping", "diplomacy", "escalation", "continue", "continues",
    "ongoing", "consecutive", "nights", "night", "second", "week", "weeks",
})

# Short org/agency tokens the default len>=4 rule would drop — live ICE miss (3 letters).
_SHORT_ORGS = frozenset({
    "ice", "fbi", "doj", "cia", "nsa", "irs", "epa", "sec", "fed", "eu", "un", "uk",
    "nato", "idf", "imf", "wto", "who", "cdc", "dhs", "cbp", "dea", "atf", "uss",
})

# Long enough to be "anchors" but too generic for a single-token family match
# (live false demotes: energy×macro energy piece; access×FDA; concern×AI credit).
_WEAK_ANCHORS = frozenset({
    "energy", "access", "market", "markets", "concern", "concerns", "credit", "stress",
    "implication", "implications", "development", "regional", "significance",
    "strategic", "arrangement", "cooperation", "criticism", "pressure", "process",
    "export", "supply", "effect", "downstream", "confirmed", "extending", "making",
    "rather", "highest", "signal", "direct", "product", "release", "research",
    "concrete", "dataset", "economic", "economy", "inside", "turning", "possible",
    "wartime", "entangled", "signaling", "drawing", "policy", "middle", "outcome",
    "outcomes", "unproven", "infrastructure", "heading", "toward", "towards",
    "warning", "warned", "record", "still", "whether", "forces", "central", "banks",
    "shipping", "diplomacy", "escalation", "continue", "continues", "ongoing",
    "software", "faulty", "configuration", "outage", "server", "servers",
})


def _stem(token: str) -> str:
    """Light plural fold so arrest/arrests match (not full NLP)."""
    if len(token) >= 5 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def significant_tokens(text: str) -> frozenset[str]:
    """Content-bearing tokens for overlap — short glue words dropped; plurals folded."""
    raw: set[str] = set()
    for m in _TOKEN.finditer(text or ""):
        t = m.group(0).lower()
        if t.isdigit() or t in _STOP:
            continue
        if len(t) >= 4 or t in _SHORT_ORGS:
            raw.add(_stem(t))
    return frozenset(raw)


def anchors(text: str) -> frozenset[str]:
    """Longer tokens / short org names that name a place, org, product — family anchors."""
    out: set[str] = set()
    for t in significant_tokens(text):
        if len(t) >= _ANCHOR_LEN or t in _SHORT_ORGS:
            out.add(t)
    return frozenset(out)


def cooled_by(
    text: str, recent_titles: list[str],
) -> tuple[bool, str]:
    """Whether ``text`` is the same story-family as something we already published.

    Returns (cooled, reason). Reason names the matching prior title or saturated keys.
    """
    if not recent_titles:
        return False, ""
    cand = significant_tokens(text)
    cand_anch = anchors(text)
    if not cand:
        return False, ""

    for title in recent_titles:
        prior = significant_tokens(title)
        if not prior:
            continue
        shared = cand & prior
        shared_anch = cand_anch & anchors(title)
        # Strong anchors only for single-token family match (ICE, Hormuz, SharePoint…).
        strong_anch = {a for a in shared_anch if a not in _WEAK_ANCHORS}
        if strong_anch:
            return True, f"anchor {sorted(strong_anch)[0]!r} also in prior: {title[:80]}"
        if len(shared) >= _MIN_SHARED:
            return True, f"{len(shared)} shared tokens with prior: {title[:80]}"

    # Saturation: a token already on the site twice is a beat we are actively covering.
    counts: Counter[str] = Counter()
    for title in recent_titles:
        counts.update(significant_tokens(title))
    saturated = {
        t for t, n in counts.items()
        if n >= _SATURATION_COUNT and (len(t) >= _ANCHOR_LEN or t in _SHORT_ORGS)
    }
    hit = sorted(cand & saturated)
    if hit:
        return True, f"saturated beat key(s) {hit[:4]} (appear in {_SATURATION_COUNT}+ recent titles)"
    return False, ""


def demote_cooled(
    ranking: RouteRanking,
    candidates: list[RouteCandidate],
    recent: tuple[tuple[str, str], ...],
) -> RouteRanking:
    """Reorder so no cooled candidate sits above a non-cooled one; re-stamp ranks 1..n.

    Cooled items stay in the list (on-deck / audit) — they just cannot promote as #1 while the
    family is hot. If every candidate is cooled, the ranking is unchanged (better a same-beat
    piece than a silent empty promote) but the note still records the miss.
    """
    if not ranking.choices:
        return ranking
    if not recent:
        note_bits = [ranking.note.strip()] if ranking.note.strip() else []
        note_bits.append("mechanical cooldown: no recent headlines available (cooldown inactive)")
        return ranking.model_copy(update={"note": " | ".join(note_bits)})

    titles = [t for _, t in recent]
    by_id = {c.id: c for c in candidates}

    free: list = []
    cooled: list = []
    reasons: list[str] = []
    for ch in ranking.choices:
        cand = by_id.get(ch.candidate_id)
        blob = f"{cand.label} {cand.summary}" if cand else ch.candidate_id
        is_cool, why = cooled_by(blob, titles)
        if is_cool:
            cooled.append(ch)
            reasons.append(f"{ch.candidate_id}: {why}")
        else:
            free.append(ch)

    note_bits = [ranking.note.strip()] if ranking.note.strip() else []
    if not cooled:
        note_bits.append(
            f"mechanical cooldown: 0/{len(ranking.choices)} choices cooled "
            f"(n_recent={len(titles)})"
        )
        return ranking.model_copy(update={"note": " | ".join(note_bits)})

    if not free:
        # All on-deck cooled — leave LLM order but make the miss visible.
        note_bits.append(
            "mechanical cooldown: ALL ranked choices cooled — left LLM order "
            f"(cannot demote): {'; '.join(reasons[:6])}"
        )
        return ranking.model_copy(update={"note": " | ".join(note_bits)})

    reordered = free + cooled
    new_choices = [
        ch.model_copy(update={"rank": i})
        for i, ch in enumerate(reordered, start=1)
    ]
    note_bits.append(
        "mechanical cooldown demoted "
        + f"{len(cooled)} already-covered famil{'y' if len(cooled) == 1 else 'ies'} below fresh stories: "
        + "; ".join(reasons[:6])
    )
    return ranking.model_copy(update={"choices": new_choices, "note": " | ".join(note_bits)})
