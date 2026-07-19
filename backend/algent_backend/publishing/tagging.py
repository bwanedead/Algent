"""
Tags + country flags — DERIVED from the profile (and vector geography), never generated.

The data already exists: the researcher named the entities, the synthesizer named the pillars and
scope. So categorisation costs no model call and cannot hallucinate — it is a pure function of the
evidence.

Two tiers, deliberately:
- TOPIC tags come from a small CANONICAL vocabulary. Pillars are free-form and already fragmenting
  in real runs ("economics", "energy", "shipping", "freight", "US-Iran conflict" in one vector), so
  mapping them into a fixed set is what stops the tag space degenerating into near-duplicates
  ("economics" vs "economic policy") that no search or index could ever unify.
- ENTITY tags stay free-form (Iran, Strait of Hormuz, OPEC): entity ids are content-addressed, so
  they dedupe themselves, and their whole value is specificity.

Flags are the "where" at a glance for browsing. They are matched on NAME, not on
``type == "place"``: the model's typing is unreliable in practice (a real run typed *Iran* and
*United States* as ``org``). Geography also lives in the vector's ``scope`` (and sometimes only
there — a UK politics profile may entity-ify people and parties without ever listing "United
Kingdom"). We harvest from every reliable field we have, then map only through a deliberate ISO
table. Unmapped text yields NO flag — never invent one to fill space.
"""

from __future__ import annotations

import re

_TAG_CAP = 5
_FLAG_CAP = 3  # enough for a multi-country story; more is noise on the feed

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
# which is the correct outcome (never invent a flag to fill space). Aliases are matching keys only;
# the display name prefers a stable canonical form per ISO (see _ISO_DISPLAY).
_COUNTRY_ISO: dict[str, str] = {
    "iran": "IR", "israel": "IL", "oman": "OM", "yemen": "YE", "saudi arabia": "SA",
    "united arab emirates": "AE", "uae": "AE", "qatar": "QA", "kuwait": "KW", "iraq": "IQ",
    "syria": "SY", "lebanon": "LB", "turkey": "TR", "türkiye": "TR", "egypt": "EG",
    "united states": "US", "united states of america": "US", "usa": "US", "u.s.": "US",
    "u.s.a.": "US", "america": "US",
    "united kingdom": "GB", "uk": "GB", "u.k.": "GB", "britain": "GB", "great britain": "GB",
    # Constituent nations map to the UK flag for feed association (no separate ISO country codes
    # for England/Scotland/Wales in the common flag-emoji set we use).
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB",
    "france": "FR", "germany": "DE",
    "italy": "IT", "spain": "ES", "netherlands": "NL", "holland": "NL", "poland": "PL", "sweden": "SE",
    "norway": "NO", "finland": "FI", "denmark": "DK", "ireland": "IE", "republic of ireland": "IE",
    "switzerland": "CH",
    "russia": "RU", "russian federation": "RU", "ukraine": "UA", "belarus": "BY", "china": "CN",
    "people's republic of china": "CN", "taiwan": "TW",
    "japan": "JP", "south korea": "KR", "republic of korea": "KR", "north korea": "KP",
    "dprk": "KP", "india": "IN", "pakistan": "PK",
    "afghanistan": "AF", "bangladesh": "BD", "indonesia": "ID", "vietnam": "VN", "philippines": "PH",
    "thailand": "TH", "malaysia": "MY", "singapore": "SG", "australia": "AU", "new zealand": "NZ",
    "canada": "CA", "mexico": "MX", "brazil": "BR", "argentina": "AR", "chile": "CL",
    "colombia": "CO", "venezuela": "VE", "peru": "PE", "cuba": "CU", "haiti": "HT",
    "nigeria": "NG", "south africa": "ZA", "kenya": "KE", "ethiopia": "ET", "sudan": "SD",
    "libya": "LY", "algeria": "DZ", "morocco": "MA", "tunisia": "TN", "ghana": "GH",
    "greece": "GR", "portugal": "PT", "austria": "AT", "belgium": "BE", "czechia": "CZ",
    "czech republic": "CZ", "hungary": "HU", "romania": "RO", "serbia": "RS", "croatia": "HR",
    "bulgaria": "BG", "european union": "EU",
}

# Stable display labels once an ISO code is known (so "UK" and "United Kingdom" collapse cleanly).
_ISO_DISPLAY: dict[str, str] = {
    "IR": "Iran", "IL": "Israel", "OM": "Oman", "YE": "Yemen", "SA": "Saudi Arabia",
    "AE": "United Arab Emirates", "QA": "Qatar", "KW": "Kuwait", "IQ": "Iraq",
    "SY": "Syria", "LB": "Lebanon", "TR": "Turkey", "EG": "Egypt",
    "US": "United States", "GB": "United Kingdom", "FR": "France", "DE": "Germany",
    "IT": "Italy", "ES": "Spain", "NL": "Netherlands", "PL": "Poland", "SE": "Sweden",
    "NO": "Norway", "FI": "Finland", "DK": "Denmark", "IE": "Ireland", "CH": "Switzerland",
    "RU": "Russia", "UA": "Ukraine", "BY": "Belarus", "CN": "China", "TW": "Taiwan",
    "JP": "Japan", "KR": "South Korea", "KP": "North Korea", "IN": "India", "PK": "Pakistan",
    "AF": "Afghanistan", "BD": "Bangladesh", "ID": "Indonesia", "VN": "Vietnam", "PH": "Philippines",
    "TH": "Thailand", "MY": "Malaysia", "SG": "Singapore", "AU": "Australia", "NZ": "New Zealand",
    "CA": "Canada", "MX": "Mexico", "BR": "Brazil", "AR": "Argentina", "CL": "Chile",
    "CO": "Colombia", "VE": "Venezuela", "PE": "Peru", "CU": "Cuba", "HT": "Haiti",
    "NG": "Nigeria", "ZA": "South Africa", "KE": "Kenya", "ET": "Ethiopia", "SD": "Sudan",
    "LY": "Libya", "DZ": "Algeria", "MA": "Morocco", "TN": "Tunisia", "GH": "Ghana",
    "GR": "Greece", "PT": "Portugal", "AT": "Austria", "BE": "Belgium", "CZ": "Czechia",
    "HU": "Hungary", "RO": "Romania", "RS": "Serbia", "HR": "Croatia", "BG": "Bulgaria",
    "EU": "European Union",
}

# Aliases shorter than this only match as exact field values (scope="UK"), never as substrings of
# longer free text — so "us" / "in" / "no" cannot fire inside ordinary English.
_MIN_SCAN_ALIAS_LEN = 3

_NON_WORD = re.compile(r"[^a-z0-9]+", re.I)


def flag_emoji(iso2: str) -> str:
    """ISO-3166 alpha-2 -> regional-indicator flag emoji (deterministic, no table needed).

    ``EU`` is not an ISO country; map it to the EU flag sequence used in Unicode (regional
    indicators for E+U still render as 🇪🇺 on modern platforms).
    """
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())


def _normalize_label(text: str) -> str:
    return _NON_WORD.sub(" ", (text or "").strip().lower()).strip()


def _iso_for_label(label: str) -> str | None:
    """Exact alias match after light normalization. No guessing."""
    key = _normalize_label(label)
    if not key:
        return None
    if key in _COUNTRY_ISO:
        return _COUNTRY_ISO[key]
    # Strip a leading "the " so "the United Kingdom" still maps.
    if key.startswith("the "):
        return _COUNTRY_ISO.get(key[4:])
    return None


def _scan_text_for_iso(text: str) -> list[str]:
    """Longest-alias-first whole-phrase scan of free text. Returns ISO codes in encounter order."""
    hay = f" {_normalize_label(text)} "
    if hay == "  ":
        return []
    # Longest first so "united states" wins over a hypothetical shorter fragment.
    aliases = sorted(
        ((a, iso) for a, iso in _COUNTRY_ISO.items() if len(a) >= _MIN_SCAN_ALIAS_LEN),
        key=lambda x: -len(x[0]),
    )
    found: list[str] = []
    seen: set[str] = set()
    for alias, iso in aliases:
        needle = f" {alias} "
        if needle in hay and iso not in seen:
            seen.add(iso)
            found.append(iso)
    return found


def _geography_fields(profile: dict, vector: dict | None) -> list[str]:
    """Every string that may name a place — entities, scope, titles. Order is priority."""
    fields: list[str] = []
    for e in (profile.get("entities") or []):
        raw = str(e.get("canonical_name") or e.get("name") or "").strip()
        if raw:
            fields.append(raw)
    vector = vector or {}
    for item in (vector.get("scope") or []):
        s = str(item).strip()
        if s:
            fields.append(s)
    for key in ("title", "thesis", "rationale"):
        s = str(vector.get(key) or "").strip()
        if s:
            fields.append(s)
    # Profile title is a weak but useful fallback when scope was empty.
    pt = str(profile.get("title") or "").strip()
    if pt:
        fields.append(pt)
    return fields


def derive_places(
    profile: dict, vector: dict | None = None, *, cap: int = _FLAG_CAP,
) -> tuple[list[str], list[str]]:
    """(country display names, flag emoji) for the places the story is about.

    Harvest order:
      1. Exact entity / scope labels (highest trust — a scope of ``UK`` is intentional geography).
      2. Phrase scan of titles/theses for mapped country names (secondary — only whole aliases).

    Cap keeps the feed scannable. Unmapped geography is simply omitted.
    """
    ordered_iso: list[str] = []
    seen: set[str] = set()

    def _add(iso: str | None) -> None:
        if not iso or iso in seen or len(ordered_iso) >= cap:
            return
        seen.add(iso)
        ordered_iso.append(iso)

    fields = _geography_fields(profile, vector)
    # Pass 1: exact labels (entity "Iran", scope "UK", scope "United Kingdom").
    for field in fields:
        # Scope entries are often short exact codes; entity names are often exact countries.
        # Also try each slash/comma segment ("Labour Party / UK government" → try both halves).
        parts = re.split(r"[/,|;]+", field)
        for part in ([field] + parts):
            _add(_iso_for_label(part))
            if len(ordered_iso) >= cap:
                break
        if len(ordered_iso) >= cap:
            break

    # Pass 2: phrase scan of longer free text (titles), only if we still have room.
    if len(ordered_iso) < cap:
        for field in fields:
            if len(field) < 8:          # short labels already tried exactly; skip re-scan noise
                continue
            for iso in _scan_text_for_iso(field):
                _add(iso)
                if len(ordered_iso) >= cap:
                    break
            if len(ordered_iso) >= cap:
                break

    names = [_ISO_DISPLAY.get(iso, iso) for iso in ordered_iso]
    flags = [flag_emoji(iso) for iso in ordered_iso]
    return names, flags


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
    # Also skip any entity that is itself a mapped country alias (flags already cover them).
    for e in (profile.get("entities") or []):
        raw = str(e.get("canonical_name") or e.get("name") or "").strip()
        if _iso_for_label(raw):
            skip.add(raw.lower())
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
    places, flags = derive_places(profile, vector)
    # Budget the bar so the specific always survives the cap: a bar of five generic topics tells the
    # reader less than "energy · trade · Strait of Hormuz". Topics set the shelf, entities say which
    # story it is — so both get guaranteed room rather than competing for one list.
    topics = derive_topics(vector.get("pillars") or [], vector.get("scope") or [], cap=3)
    entities = derive_entity_tags(profile, cap=_TAG_CAP - len(topics), exclude=places)
    return {"tags": [*topics, *entities], "places": places, "flags": flags}
