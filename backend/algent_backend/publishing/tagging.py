"""
Tags + country flags.

- TOPIC / ENTITY tags: still derived from profile pillars/entities (deterministic).
- FLAGS / PLACES: come ONLY from the agent's ``countries_of_relevance`` contract field
  on the signal profile. No lexical scan of titles, entities, or scope for flags.

Why: live failures (Nicaragua story → US flag because Rubio was mentioned; ICE story →
no flag because "United States" never landed as an exact entity). Geography for the feed
is a semantic judgment the researcher already makes — capture it in the contract, render
it to ISO flag emoji/PNG. The country table lives in ``actors/registry.py`` (the one table in the
codebase); here it is only a *renderer* (name + iso2 → display), not a story identifier.
"""

from __future__ import annotations

import re

from algent_backend.actors import registry

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

_ISO2_RE = re.compile(r"^[A-Za-z]{2}$")


def flag_emoji(iso2: str) -> str:
    """ISO-3166 alpha-2 -> regional-indicator flag emoji (deterministic)."""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso2.upper())


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
        iso = registry.resolve(name)
    if not iso:
        return None
    display = name or registry.display_name(iso, iso)
    return iso, display


def iso2_for_name(name: str) -> str:
    """ISO-3166 alpha-2 for a country NAME the caller already judged semantically (a statement's
    affiliation, a Pulse's principal actor), or "" when the name is not a country in the registry
    (NATO, the UN, a company). Renderer only: it identifies nothing, it spells."""
    found = _resolve_country_entry({"name": name})
    return found[0] if found else ""


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
