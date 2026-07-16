"""
Tags + country flags — DERIVED from the profile, never generated.

The data already exists: the researcher named the entities, the synthesizer named the pillars. So
categorisation costs no model call and cannot hallucinate — it is a pure function of the evidence.

Two tiers, deliberately:
- TOPIC tags come from a small CANONICAL vocabulary. Pillars are free-form and already fragmenting
  in real runs ("economics", "energy", "shipping", "freight", "US-Iran conflict" in one vector), so
  mapping them into a fixed set is what stops the tag space degenerating into near-duplicates
  ("economics" vs "economic policy") that no search or index could ever unify.
- ENTITY tags stay free-form (Iran, Strait of Hormuz, OPEC): entity ids are content-addressed, so
  they dedupe themselves, and their whole value is specificity.

Flags are matched on entity NAME across every entity, not on ``type == "place"``: the model's typing
is unreliable in practice (a real run typed *Iran* and *United States* as ``org``), and a missing
flag beats a wrong one. Anything that doesn't map cleanly is simply skipped — we never guess.
"""

from __future__ import annotations

_TAG_CAP = 5

# canonical topic -> substrings that imply it (matched against free-form pillars/scope)
_TOPIC_VOCAB: dict[str, tuple[str, ...]] = {
    "economics": ("econom", "inflation", "macro", "gdp", "fiscal", "central bank", "rates"),
    "markets": ("market", "equit", "bond", "commodit", "trading", "stock", "invest"),
    "energy": ("energy", "oil", "gas", "lng", "petrol", "opec", "crude", "pipeline"),
    "trade": ("trade", "shipping", "freight", "supply chain", "tariff", "export", "import", "logistic", "port"),
    "geopolitics": ("geopolit", "diplomat", "sanction", "foreign polic", "alliance", "treaty"),
    "conflict": ("conflict", "war", "militar", "strike", "attack", "blockade", "clash", "invasion"),
    "security": ("security", "defen", "terror", "cyber", "intelligence"),
    "politics": ("politic", "election", "parliament", "congress", "government", "legislat"),
    "technology": ("tech", "software", "chip", "semiconductor", "artificial intelligence", " ai"),
    "climate": ("climate", "emission", "warming", "carbon", "renewable"),
    # Pharma/clinical vocabulary is load-bearing, not an afterthought: a live run tagged an FDA
    # drug approval "economics" over "health" purely because none of pharma/drug/FDA/trial were
    # here to match. Domain gaps in this table read as bad ranking; they're really absence.
    "health": ("health", "disease", "pandemic", "medical", "vaccine", "outbreak", "pharma",
               "drug", "clinical", "fda", "trial", "therap", "patient", "cardio", "oncolog"),
    "science": ("science", "research", "space", "physics", "biolog", "chemist"),
    "business": ("business", "corporate", "merger", "earnings", "company", "industry"),
    "law": ("law", "legal", "court", "ruling", "prosecut", "regulat"),
}

# Newsworthy countries -> ISO-3166 alpha-2. Deliberately partial: an unmapped name yields NO flag,
# which is the correct outcome (never invent a flag to fill space).
_COUNTRY_ISO: dict[str, str] = {
    "iran": "IR", "israel": "IL", "oman": "OM", "yemen": "YE", "saudi arabia": "SA",
    "united arab emirates": "AE", "uae": "AE", "qatar": "QA", "kuwait": "KW", "iraq": "IQ",
    "syria": "SY", "lebanon": "LB", "turkey": "TR", "türkiye": "TR", "egypt": "EG",
    "united states": "US", "united states of america": "US", "usa": "US", "u.s.": "US", "america": "US",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "france": "FR", "germany": "DE",
    "italy": "IT", "spain": "ES", "netherlands": "NL", "poland": "PL", "sweden": "SE",
    "norway": "NO", "finland": "FI", "denmark": "DK", "ireland": "IE", "switzerland": "CH",
    "russia": "RU", "ukraine": "UA", "belarus": "BY", "china": "CN", "taiwan": "TW",
    "japan": "JP", "south korea": "KR", "north korea": "KP", "india": "IN", "pakistan": "PK",
    "afghanistan": "AF", "bangladesh": "BD", "indonesia": "ID", "vietnam": "VN", "philippines": "PH",
    "thailand": "TH", "malaysia": "MY", "singapore": "SG", "australia": "AU", "new zealand": "NZ",
    "canada": "CA", "mexico": "MX", "brazil": "BR", "argentina": "AR", "chile": "CL",
    "colombia": "CO", "venezuela": "VE", "peru": "PE", "cuba": "CU", "haiti": "HT",
    "nigeria": "NG", "south africa": "ZA", "kenya": "KE", "ethiopia": "ET", "sudan": "SD",
    "libya": "LY", "algeria": "DZ", "morocco": "MA", "tunisia": "TN", "ghana": "GH",
    "greece": "GR", "portugal": "PT", "austria": "AT", "belgium": "BE", "czechia": "CZ",
    "hungary": "HU", "romania": "RO", "serbia": "RS", "croatia": "HR", "bulgaria": "BG",
}


def flag_emoji(iso2: str) -> str:
    """ISO-3166 alpha-2 -> regional-indicator flag emoji (deterministic, no table needed)."""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())


def derive_topics(pillars: list[str], scope: list[str] | None = None, *, cap: int = 3) -> list[str]:
    """Free-form pillars/scope -> the canonical topics they imply (stable, unionable, searchable).

    RANKED by how many of a topic's markers actually hit, because broad pillars trip several topics
    at once and an unranked list buries the specific under the generic: the Hormuz vector matched
    five topics, of which "energy"/"trade" are what the story IS and "economics"/"markets" are
    ambient. Strongest signal first, then cap.
    """
    pillar_hay = " ".join(str(x).lower() for x in (pillars or []))
    scope_hay = " ".join(str(x).lower() for x in (scope or []))
    # A PILLAR match outweighs a SCOPE match: pillars say what the story is, scope says where it
    # sits. Unweighted, ties broke on dict order and the Hormuz piece tagged "economics · markets"
    # (both ambient — "markets" came only from the scope "global markets") while dropping "energy"
    # and "conflict", which is what it was actually about.
    scored = [
        (sum(2 for n in needles if n in pillar_hay) + sum(1 for n in needles if n in scope_hay), topic)
        for topic, needles in _TOPIC_VOCAB.items()
    ]
    return [topic for hits, topic in sorted(scored, key=lambda s: -s[0]) if hits][:cap]


def derive_places(profile: dict) -> tuple[list[str], list[str]]:
    """(country names, flag emoji) mentioned as entities. Matches on NAME across ALL entity types —
    the model's `type` is unreliable (it has typed *Iran* as an org) — and skips anything unmapped."""
    names: list[str] = []
    for e in (profile.get("entities") or []):
        raw = str(e.get("canonical_name") or e.get("name") or "").strip()
        iso = _COUNTRY_ISO.get(raw.lower())
        if iso and raw not in names:
            names.append(raw)
    return names, [flag_emoji(_COUNTRY_ISO[n.lower()]) for n in names]


def derive_entity_tags(profile: dict, *, cap: int = 3, exclude: list[str] | None = None) -> list[str]:
    """The entities this story is ABOUT, most-referenced first.

    Entities carry no salience of their own, so rank by how often the field REFERENCES them (threads
    link the entities they touch) — a proxy for load-bearing that needs no model call.

    Two deterministic exclusions, both learned from real output:
    - COUNTRIES render as flags; showing 🇮🇷 and an "Iran" tag is the same fact twice.
    - SOURCE ORGS are who we READ, not what the story is about. The researcher entity-ifies them
      (a live profile produced "Reuters", "Kpler", "U.S. Energy Information Administration"), and
      tagging a piece "Reuters" tells the reader nothing about the world. The source ledger already
      names them, so this is a free, exact filter.
    """
    skip = {s.lower() for s in (exclude or [])}
    for s in (profile.get("source_ledger") or []):
        for field in ("publisher", "author"):
            if val := str(s.get(field) or "").strip().lower():
                skip.add(val)
    by_id = {e.get("id"): str(e.get("name") or "") for e in (profile.get("entities") or [])}
    refs: dict[str, int] = {eid: 0 for eid in by_id}
    for t in (profile.get("threads") or []):
        for eid in (t.get("entities") or []):
            if eid in refs:
                refs[eid] += 1
    ranked = sorted(by_id, key=lambda eid: (-refs[eid], by_id[eid]))
    out: list[str] = []
    for eid in ranked:
        name = by_id[eid]
        if name and name.lower() not in skip and name not in out:
            out.append(name)
        if len(out) >= cap:
            break
    return out


def derive_all(profile: dict, vector: dict | None = None) -> dict[str, list[str]]:
    """Everything the frontmatter needs: canonical topics + entity tags + places/flags."""
    vector = vector or {}
    places, flags = derive_places(profile)
    # Budget the bar so the specific always survives the cap: a bar of five generic topics tells the
    # reader less than "energy · trade · Strait of Hormuz". Topics set the shelf, entities say which
    # story it is — so both get guaranteed room rather than competing for one list.
    topics = derive_topics(vector.get("pillars") or [], vector.get("scope") or [], cap=3)
    entities = derive_entity_tags(profile, cap=_TAG_CAP - len(topics), exclude=places)
    return {"tags": [*topics, *entities], "places": places, "flags": flags}
