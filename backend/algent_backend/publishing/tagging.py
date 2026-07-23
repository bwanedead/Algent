"""
Tags + country flags.

- TOPIC / ENTITY tags: still derived from profile pillars/entities (deterministic).
- FLAGS / PLACES: come ONLY from the agent's ``countries_of_relevance`` contract field
  on the signal profile. No lexical scan of titles, entities, or scope for flags.

Why: live failures (Nicaragua story → US flag because Rubio was mentioned; ICE story →
no flag because "United States" never landed as an exact entity). Geography for the feed
is a semantic judgment the researcher already makes — capture it in the contract, render
it to ISO flag emoji/PNG. The ISO table here is a *renderer* (name + iso2 → display),
not a story identifier.
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
    "health": ("health", "disease", "pandemic", "medical", "vaccine", "outbreak", "pharma",
               "drug", "clinical", "fda", "trial", "therap", "patient", "cardio", "oncolog"),
    "science": ("science", "research", "space", "physics", "biolog", "chemist"),
    "business": ("business", "corporate", "merger", "earnings", "company", "industry"),
    "law": ("law", "legal", "court", "ruling", "prosecut", "regulat"),
}

# Display labels for known ISO codes (renderer only).
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
    "NI": "Nicaragua", "CR": "Costa Rica", "PA": "Panama", "GT": "Guatemala", "HN": "Honduras",
    "SV": "El Salvador", "BZ": "Belize",
    "NG": "Nigeria", "ZA": "South Africa", "KE": "Kenya", "ET": "Ethiopia", "UG": "Uganda",
    "SS": "South Sudan", "SD": "Sudan",
    "CD": "Democratic Republic of the Congo", "CG": "Republic of the Congo",
    "LY": "Libya", "DZ": "Algeria", "MA": "Morocco", "TN": "Tunisia", "GH": "Ghana",
    "GR": "Greece", "PT": "Portugal", "AT": "Austria", "BE": "Belgium", "CZ": "Czechia",
    "HU": "Hungary", "RO": "Romania", "RS": "Serbia", "HR": "Croatia", "BG": "Bulgaria",
    "EU": "European Union",
}

# Optional name → ISO when the agent fills name but botches iso2 (still not story-scan).
_NAME_TO_ISO: dict[str, str] = {
    "nicaragua": "NI", "united states": "US", "usa": "US", "u.s.": "US", "america": "US",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "iran": "IR", "israel": "IL",
    "russia": "RU", "ukraine": "UA", "china": "CN", "germany": "DE", "france": "FR",
    "saudi arabia": "SA", "yemen": "YE", "lebanon": "LB", "syria": "SY", "iraq": "IQ",
    "turkey": "TR", "egypt": "EG", "india": "IN", "japan": "JP", "south korea": "KR",
    "north korea": "KP", "australia": "AU", "canada": "CA", "mexico": "MX", "brazil": "BR",
    "south africa": "ZA", "kenya": "KE", "ethiopia": "ET", "uganda": "UG",
    "democratic republic of the congo": "CD", "south sudan": "SS", "sudan": "SD",
    "european union": "EU", "croatia": "HR", "spain": "ES", "italy": "IT",
    "netherlands": "NL", "poland": "PL", "sweden": "SE", "norway": "NO",
}

_ISO2_RE = re.compile(r"^[A-Za-z]{2}$")
_NON_WORD = re.compile(r"[^a-z0-9]+", re.I)


def flag_emoji(iso2: str) -> str:
    """ISO-3166 alpha-2 -> regional-indicator flag emoji (deterministic)."""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())


def _normalize_label(text: str) -> str:
    return _NON_WORD.sub(" ", (text or "").strip().lower()).strip()


def _normalize_iso2(raw: str) -> str | None:
    code = (raw or "").strip().upper()
    if code == "UK":
        code = "GB"
    if not _ISO2_RE.match(code):
        return None
    return code


def _resolve_country_entry(entry: object) -> tuple[str, str] | None:
    """(iso2, display_name) from a CountryOfRelevance-like dict/object, or None if unusable."""
    if isinstance(entry, dict):
        iso_raw = entry.get("iso2") or entry.get("iso") or entry.get("code") or ""
        name = str(entry.get("name") or "").strip()
    else:
        iso_raw = getattr(entry, "iso2", None) or getattr(entry, "iso", None) or ""
        name = str(getattr(entry, "name", "") or "").strip()

    iso = _normalize_iso2(str(iso_raw))
    if not iso and name:
        iso = _NAME_TO_ISO.get(_normalize_label(name))
    if not iso:
        return None
    display = name or _ISO_DISPLAY.get(iso, iso)
    return iso, display


def derive_places(
    profile: dict, vector: dict | None = None, *, cap: int = _FLAG_CAP,
) -> tuple[list[str], list[str]]:
    """(country display names, flag emoji) from agent ``countries_of_relevance`` only.

    No lexical harvest of entities/titles. Empty contract → empty flags (never invent US
    because a US official was named).
    """
    del vector  # geography is not scanned from the vector anymore
    raw = profile.get("countries_of_relevance") or []
    ordered_iso: list[str] = []
    names: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        resolved = _resolve_country_entry(entry)
        if not resolved:
            continue
        iso, display = resolved
        if iso in seen:
            continue
        seen.add(iso)
        ordered_iso.append(iso)
        names.append(display)
        if len(ordered_iso) >= cap:
            break
    flags = [flag_emoji(iso) for iso in ordered_iso]
    return names, flags


def derive_topics(pillars: list[str], scope: list[str] | None = None, *, cap: int = 3) -> list[str]:
    """Free-form pillars/scope -> the canonical topics they imply."""
    pillar_hay = " ".join(str(x).lower() for x in (pillars or []))
    scope_hay = " ".join(str(x).lower() for x in (scope or []))
    scored = [
        (sum(2 for n in needles if n in pillar_hay) + sum(1 for n in needles if n in scope_hay), topic)
        for topic, needles in _TOPIC_VOCAB.items()
    ]
    return [topic for hits, topic in sorted(scored, key=lambda s: -s[0]) if hits][:cap]


def derive_entity_tags(profile: dict, *, cap: int = 3, exclude: list[str] | None = None) -> list[str]:
    """The entities this story is ABOUT, most-referenced first."""
    skip = {s.lower() for s in (exclude or [])}
    # Skip entities that match declared countries of relevance (flags cover them).
    for c in (profile.get("countries_of_relevance") or []):
        resolved = _resolve_country_entry(c)
        if resolved:
            skip.add(resolved[1].lower())
        if isinstance(c, dict) and c.get("name"):
            skip.add(str(c["name"]).lower())
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
    topics = derive_topics(vector.get("pillars") or [], vector.get("scope") or [], cap=3)
    entities = derive_entity_tags(profile, cap=_TAG_CAP - len(topics), exclude=places)
    return {"tags": [*topics, *entities], "places": places, "flags": flags}
