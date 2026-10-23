"""Entity identity in the corpus index: kind precedence (a country beats a same-named place), merging of one real thing declared under several ids,
and the guarantees around it (merged ids stay resolvable, genuine ambiguity stays reported, assets never merge on a name)."""

from __future__ import annotations

from pathlib import Path

import pytest

from algent_backend import corpus
from algent_backend.agent_system.agents.research.profile import Entity, SignalProfile
from algent_backend.agent_system.agents.research.store import JsonProfileStore
from algent_backend.corpus import identity, link, schema
from algent_backend.corpus.query import resolve
from algent_backend.corpus.sink import Sink

NOW = "2026-10-23T00:00:00+00:00"


@pytest.fixture()
def db(tmp_path: Path):
    conn = schema.connect(tmp_path / "c.db", write=True)
    conn.isolation_level = None
    schema.create(conn, fts=False)
    yield conn
    conn.close()


def unit(db, name: str, product: str = "profiles") -> Sink:
    return Sink(db, product, name, NOW)


def finish(db) -> tuple[int, bool]:
    db.execute("BEGIN")
    out = link.finish(db)
    db.execute("COMMIT")
    return out


def resolved(db, text: str) -> str | None:
    return db.execute("SELECT entity_id FROM mentions WHERE surface = ?", (text,)).fetchone()[0]


def test_country_beats_a_place_and_an_org_of_the_same_name(db):
    unit(db, "reg", "actors").declare("country:FR", "country", "France", iso2="FR", rank=0)
    unit(db, "geo", "geoledger").declare("asset:fr-1", "place", "France", rank=5)
    unit(db, "p", "profiles").declare("org:france", "org", "France", rank=9)
    unit(db, "doc").mention(surface="France", document="d1")
    finish(db)
    assert resolved(db, "France") == "country:FR"


def test_same_tier_collision_of_different_kinds_stays_ambiguous(db):
    unit(db, "a").declare("person:jordan", "person", "Jordan", rank=9)
    unit(db, "b").declare("place:jordan-river", "place", "Jordan", rank=9)
    unit(db, "doc").mention(surface="Jordan", document="d1")
    finish(db)
    assert resolved(db, "Jordan") is None
    row = link.unresolved(db)[0]
    assert (row["name"], row["reason"]) == ("Jordan", "ambiguous")


def test_two_profiles_naming_one_org_become_one_entity(db):
    unit(db, "p1").declare("org:houthi-movement", "org", "Houthi movement", aliases=["Houthis", "Ansar Allah"], rank=9)
    unit(db, "p2").declare("org:houthis", "org", "Houthis", rank=9)
    s = unit(db, "p2")
    s.mention(entity="org:houthis", document="d1")
    s.mention(surface="Ansar Allah", document="d1")
    unit(db, "o").observation("x", "2026-10-01", 1.0, entity="org:houthis")
    n, ok = finish(db)
    assert ok
    ids = [r[0] for r in db.execute("SELECT id FROM entities WHERE kind = 'org'")]
    assert ids == ["org:houthi-movement"]                                  # the smaller id is canonical on a tie of rank
    assert db.execute("SELECT entity_id FROM mentions WHERE document_id = 'd1' AND asserted = 1").fetchone()[0] == "org:houthi-movement"
    assert db.execute("SELECT entity_id FROM observations").fetchone()[0] == "org:houthi-movement"
    assert resolved(db, "Ansar Allah") == "org:houthi-movement"
    assert dict(db.execute("SELECT old_id, canon_id FROM entity_merge").fetchall()) == {"org:houthis": "org:houthi-movement"}
    assert resolve.find(db, "org:houthis")[0]["id"] == "org:houthi-movement"       # the folded id still opens the entity
    assert {a for a in resolve.find(db, "Houthis")[0]["aliases"]} >= {"Houthis", "Ansar Allah"}


def test_a_better_ranked_declaration_names_the_merged_entity(db):
    unit(db, "inst", "instruments").declare("place:chokepoint:strait-of-hormuz", "place", "Strait of Hormuz", lat=26.5, lon=56.3, rank=5)
    unit(db, "prof").declare("place:strait-of-hormuz", "place", "Strait of Hormuz", rank=9)
    unit(db, "st").declare("topic:strait-of-hormuz", "topic", "Strait of Hormuz", rank=9)
    unit(db, "doc").mention(surface="Strait of Hormuz", document="d1")
    finish(db)
    places = db.execute("SELECT id, lat FROM entities WHERE kind = 'place'").fetchall()
    assert [(r[0], r[1]) for r in places] == [("place:chokepoint:strait-of-hormuz", 26.5)]
    assert resolved(db, "Strait of Hormuz") == "place:chokepoint:strait-of-hormuz"      # no longer ambiguous with the profile's twin


def test_an_untyped_speaker_folds_into_the_typed_entity_of_its_name(db):
    unit(db, "prof").declare("org:un-security-council", "org", "UN Security Council", aliases=["UNSC"], rank=9)
    unit(db, "stm", "statements").declare("actor:un-security-council", "actor", "UN Security Council", rank=10)
    unit(db, "stm", "statements").mention(entity="actor:un-security-council", document="st1")
    finish(db)
    assert [r[0] for r in db.execute("SELECT id FROM entities")] == ["org:un-security-council"]
    assert db.execute("SELECT entity_id FROM mentions WHERE document_id = 'st1'").fetchone()[0] == "org:un-security-council"


def test_an_org_known_by_its_acronym_merges_with_the_spelled_out_one(db):
    unit(db, "a").declare("org:international-criminal-court", "org", "International Criminal Court", aliases=["ICC"], rank=9)
    unit(db, "b").declare("org:icc", "org", "ICC", rank=9)
    unit(db, "doc").mention(surface="ICC", document="d1")
    finish(db)
    assert db.execute("SELECT COUNT(*) FROM entities WHERE kind = 'org'").fetchone()[0] == 1
    assert resolved(db, "ICC") == "org:icc" or resolved(db, "ICC") == "org:international-criminal-court"


def test_two_orgs_that_only_share_an_alias_stay_apart(db):
    unit(db, "a").declare("org:international-criminal-court", "org", "International Criminal Court", aliases=["ICC"], rank=9)
    unit(db, "b").declare("org:international-cricket-council", "org", "International Cricket Council", aliases=["ICC"], rank=9)
    unit(db, "doc").mention(surface="ICC", document="d1")
    finish(db)
    assert db.execute("SELECT COUNT(*) FROM entities WHERE kind = 'org'").fetchone()[0] == 2
    assert resolved(db, "ICC") is None and link.unresolved(db)[0]["reason"] == "ambiguous"


def test_geoledger_assets_never_merge_on_a_name(db):
    for i in (1, 2):
        unit(db, f"g{i}", "geoledger").declare(f"asset:p{i}", "place", "Kariba", lat=float(i), lon=float(i), rank=5)
    finish(db)
    assert db.execute("SELECT COUNT(*) FROM entities WHERE kind = 'place'").fetchone()[0] == 2


def test_merge_monotone_only_when_nothing_is_split():
    assert identity.merge_is_monotone({"b": "a"}, {"b": "a"})
    assert identity.merge_is_monotone({"b": "a"}, {"b": "a", "c": "a"})
    assert identity.merge_is_monotone({"b": "a"}, {"b": "0", "a": "0"})        # a better canonical took over: still one set
    assert not identity.merge_is_monotone({"b": "a"}, {})                      # a revision stopped sharing a name: cannot be undone in place
    assert not identity.merge_is_monotone({"b": "a"}, {"a": "z"})              # the old canonical left the set that b stayed in


def test_a_second_finish_changes_nothing(db):
    unit(db, "p1").declare("org:houthi-movement", "org", "Houthi movement", aliases=["Houthis"], rank=9)
    unit(db, "p2").declare("org:houthis", "org", "Houthis", rank=9)
    unit(db, "p2").mention(entity="org:houthis", document="d1")
    finish(db)
    first = [tuple(r) for r in db.execute("SELECT * FROM mentions ORDER BY id")] + [tuple(r) for r in db.execute("SELECT * FROM entities ORDER BY id")]
    _, ok = finish(db)
    assert ok and first == [tuple(r) for r in db.execute("SELECT * FROM mentions ORDER BY id")] + [tuple(r) for r in db.execute("SELECT * FROM entities ORDER BY id")]


STORES = {"ALGENT_INTEL_STORE": "intel", "ALGENT_PULSE_STORE": "pulse", "ALGENT_PROFILE_STORE": "profiles", "ALGENT_STATEMENTS_STORE": "statements",
          "ALGENT_SANCTIONS_STORE": "sanctions", "ALGENT_CALENDAR_STORE": "calendar", "ALGENT_INSTRUMENTS_STORE": "instruments",
          "ALGENT_ACTORS_STORE": "actors", "ALGENT_GEOLEDGER_STORE": "geo", "ALGENT_MARKETS_STORE": "markets", "ALGENT_MARITIME_STORE": "maritime",
          "ALGENT_AI_BENCHMARKS_STORE": "bench", "ALGENT_CORPUS_STORE": "corpus"}


def test_an_identity_split_makes_the_incremental_build_start_over(tmp_path, monkeypatch):
    for env, name in STORES.items():
        monkeypatch.setenv(env, str(tmp_path / name))
    from algent_backend.ops.products import locations
    monkeypatch.setattr(locations, "site_articles", lambda: tmp_path / "no-articles")
    store = JsonProfileStore()
    save = lambda pid, ent: store.save(SignalProfile(id=pid, title=pid, summary="s", as_of="2026-10-01", generated_at="2026-10-01T00:00:00+00:00", entities=[ent]))  # noqa: E731
    save("prof_a", Entity(id="e1", name="Houthi movement", type="org", aliases=["Houthis"]))
    save("prof_b", Entity(id="e1", name="Houthis", type="org"))
    assert corpus.build(full=True)["full"]
    with corpus.Corpus.open() as c:
        assert [e["id"] for e in c.find("Houthis")] == ["org:houthi-movement"]
    save("prof_a", Entity(id="e1", name="Houthi movement", type="org"))          # a revision no longer says "Houthis"
    r = corpus.build()
    assert r["full"] and r["merge_monotone"] is not False                         # restarted from nothing, and the fresh index is consistent
    with corpus.Corpus.open() as c:
        assert {e["id"] for e in c.find("Houthis")} == {"org:houthis"}
        assert c.db.execute("SELECT COUNT(*) FROM entity_merge").fetchone()[0] == 0
