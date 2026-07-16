"""Tests for tag/flag derivation — pure functions of the profile, no model, no invention."""

from __future__ import annotations

from algent_backend.publishing import tagging as tg

# Shaped like a real profile: the model types countries inconsistently (Iran as an org — this is
# from an actual run) and entity-ifies the outlets it read.
_PROFILE = {
    "entities": [
        {"id": "e1", "name": "Iran", "type": "org"},                 # a country, mistyped
        {"id": "e2", "name": "United States", "type": "org"},        # ditto
        {"id": "e3", "name": "Strait of Hormuz", "type": "place"},
        {"id": "e4", "name": "Reuters", "type": "org"},              # a source, not a subject
        {"id": "e5", "name": "Kpler", "type": "org"},
        {"id": "e6", "name": "Joint Maritime Information Center", "type": "org"},
    ],
    "threads": [
        {"id": "t1", "entities": ["e3", "e3", "e1"]},
        {"id": "t2", "entities": ["e3", "e6"]},
    ],
    "source_ledger": [{"publisher": "Reuters"}, {"publisher": "Kpler"}],
}
_VECTOR = {"pillars": ["economics", "energy", "shipping", "US-Iran conflict", "freight"],
           "scope": ["Gulf", "global markets"]}


def test_flags_match_country_names_across_all_entity_types() -> None:
    # The model typed Iran/US as "org"; trusting `type == place` would miss the story's subject.
    names, flags = tg.derive_places(_PROFILE)
    assert names == ["Iran", "United States"] and flags == ["🇮🇷", "🇺🇸"]


def test_unmapped_places_get_no_flag_rather_than_a_wrong_one() -> None:
    names, flags = tg.derive_places({"entities": [{"id": "e", "name": "Strait of Hormuz", "type": "place"}]})
    assert names == [] and flags == []      # a strait is not a country — skip, never guess


def test_flag_emoji_is_derived_not_tabled() -> None:
    assert tg.flag_emoji("IR") == "🇮🇷" and tg.flag_emoji("ua") == "🇺🇦"


def test_topics_are_canonical_and_pillar_weighted() -> None:
    # "markets" only appears via scope ("global markets") — ambient; energy/trade are pillars.
    topics = tg.derive_topics(_VECTOR["pillars"], _VECTOR["scope"], cap=3)
    assert topics[0] == "trade"             # two pillar hits (shipping, freight)
    assert "energy" in topics and "markets" not in topics
    assert all(t in tg._TOPIC_VOCAB for t in topics)   # canonical vocabulary only — never free-form


def test_entity_tags_exclude_sources_and_countries() -> None:
    tags = tg.derive_entity_tags(_PROFILE, cap=5, exclude=["Iran", "United States"])
    assert "Strait of Hormuz" == tags[0]    # most-referenced across threads
    assert "Reuters" not in tags and "Kpler" not in tags     # who we read, not what it's about
    assert "Iran" not in tags               # renders as a flag; don't say it twice


def test_derive_all_budgets_the_bar_so_specifics_survive() -> None:
    out = tg.derive_all(_PROFILE, _VECTOR)
    assert len(out["tags"]) <= 5
    assert "Strait of Hormuz" in out["tags"]   # the specific isn't crowded out by generic topics
    assert out["flags"] == ["🇮🇷", "🇺🇸"]


def test_no_vector_still_yields_flags_and_entity_tags() -> None:
    out = tg.derive_all(_PROFILE, None)
    assert out["flags"] == ["🇮🇷", "🇺🇸"] and "Strait of Hormuz" in out["tags"]
