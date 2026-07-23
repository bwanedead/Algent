"""Tests for tag/flag derivation — flags from agent countries_of_relevance only."""

from __future__ import annotations

from algent_backend.publishing import tagging as tg

_PROFILE = {
    "countries_of_relevance": [
        {"iso2": "IR", "name": "Iran", "role": "primary"},
        {"iso2": "US", "name": "United States", "role": "actor"},
    ],
    "entities": [
        {"id": "e1", "name": "Iran", "type": "org"},
        {"id": "e2", "name": "United States", "type": "org"},
        {"id": "e3", "name": "Strait of Hormuz", "type": "place"},
        {"id": "e4", "name": "Reuters", "type": "org"},
        {"id": "e5", "name": "Kpler", "type": "org"},
        {"id": "e6", "name": "Joint Maritime Information Center", "type": "org"},
    ],
    "threads": [
        {"id": "t1", "entities": ["e3", "e3", "e1"]},
        {"id": "t2", "entities": ["e3", "e6"]},
    ],
    "source_ledger": [{"publisher": "Reuters"}, {"publisher": "Kpler"}],
}
_VECTOR = {
    "pillars": ["economics", "energy", "shipping", "US-Iran conflict", "freight"],
    "scope": ["Gulf", "global markets"],
}


def test_flags_from_agent_countries_of_relevance() -> None:
    names, flags = tg.derive_places(_PROFILE)
    assert names == ["Iran", "United States"] and flags == ["🇮🇷", "🇺🇸"]


def test_no_countries_contract_yields_no_flags() -> None:
    # No lexical fallback — empty contract means empty flags (never invent US).
    names, flags = tg.derive_places({
        "entities": [
            {"name": "United States"},
            {"name": "Marco Rubio"},
            {"name": "Nicaragua"},
        ],
        "countries_of_relevance": [],
    })
    assert names == [] and flags == []


def test_nicaragua_not_us_when_agent_declares_ni() -> None:
    # Live failure: Rubio reaction made US the only flag; agent contract fixes it.
    profile = {
        "countries_of_relevance": [
            {"iso2": "NI", "name": "Nicaragua", "role": "primary setting"},
        ],
        "entities": [
            {"name": "Daniel Ortega"},
            {"name": "Marco Rubio"},
            {"name": "United States"},
        ],
    }
    names, flags = tg.derive_places(profile)
    assert names == ["Nicaragua"] and flags == ["🇳🇮"]
    assert "United States" not in names


def test_agent_name_repairs_missing_iso() -> None:
    names, flags = tg.derive_places({
        "countries_of_relevance": [{"iso2": "", "name": "Nicaragua"}],
    })
    assert names == ["Nicaragua"] and flags == ["🇳🇮"]


def test_uk_alias_normalized() -> None:
    names, flags = tg.derive_places({
        "countries_of_relevance": [{"iso2": "UK", "name": "United Kingdom"}],
    })
    assert names[0] == "United Kingdom" and flags == ["🇬🇧"]


def test_flag_cap_keeps_the_feed_scannable() -> None:
    profile = {
        "countries_of_relevance": [
            {"iso2": "IR"}, {"iso2": "US"}, {"iso2": "GB"},
            {"iso2": "FR"}, {"iso2": "DE"},
        ],
    }
    names, flags = tg.derive_places(profile, cap=3)
    assert len(names) == 3 and len(flags) == 3


def test_flag_emoji_is_derived_not_tabled() -> None:
    assert tg.flag_emoji("IR") == "🇮🇷" and tg.flag_emoji("ua") == "🇺🇦"
    assert tg.flag_emoji("NI") == "🇳🇮"


def test_topics_are_canonical_and_pillar_weighted() -> None:
    topics = tg.derive_topics(_VECTOR["pillars"], _VECTOR["scope"], cap=3)
    assert topics[0] == "trade"
    assert "energy" in topics and "markets" not in topics
    assert all(t in tg._TOPIC_VOCAB for t in topics)


def test_pharma_story_leads_with_health_not_economics() -> None:
    topics = tg.derive_topics(["economics"], ["health", "pharma", "FDA", "cardiovascular"], cap=3)
    assert topics[0] == "health" and "economics" in topics


def test_entity_tags_exclude_sources_and_declared_countries() -> None:
    tags = tg.derive_entity_tags(_PROFILE, cap=5, exclude=["Iran", "United States"])
    assert "Strait of Hormuz" == tags[0]
    assert "Reuters" not in tags and "Kpler" not in tags
    assert "Iran" not in tags


def test_derive_all_budgets_the_bar_so_specifics_survive() -> None:
    out = tg.derive_all(_PROFILE, _VECTOR)
    assert len(out["tags"]) <= 5
    assert "Strait of Hormuz" in out["tags"]
    assert out["flags"] == ["🇮🇷", "🇺🇸"]
    assert out["places"] == ["Iran", "United States"]


def test_ice_story_agent_declares_us_only() -> None:
    out = tg.derive_all({
        "countries_of_relevance": [{"iso2": "US", "name": "United States"}],
        "entities": [
            {"id": "e1", "name": "ICE", "type": "org"},
            {"id": "e2", "name": "DHS", "type": "org"},
        ],
        "threads": [{"entities": ["e1", "e1", "e2"]}],
        "source_ledger": [],
    }, {"pillars": ["politics", "law"], "scope": []})
    assert out["flags"] == ["🇺🇸"] and out["places"] == ["United States"]
