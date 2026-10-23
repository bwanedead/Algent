"""Entity views and the search index from a (tiny) corpus index: provenance and basis on every record, the geoledger place block, and an index that only points at files that exist."""

from __future__ import annotations

from views_fixture import context

from algent_backend.views import build, country, entity, flags, search


def views_by_key(ctx) -> dict:
    return {v.key: v for v in entity.build(ctx)}


def test_entities_with_substance_get_a_view_with_provenance_and_basis(tmp_path, monkeypatch):
    monkeypatch.setattr(flags, "SEARCH_MIN_USES", 2)           # the tiny corpus has little to say about anyone
    ctx = context(tmp_path, with_corpus=True)
    views = views_by_key(ctx)
    irgc = views["entity/org/irgc"].body
    assert irgc["kind"] == "org" and "Revolutionary Guards" in irgc["aliases"] and irgc["counts"]["documents"] == 1
    doc = irgc["documents"][0]
    assert doc["product"] == "profiles" and doc["origin"] == "profile:p1" and "ingested_at" not in doc
    claim = irgc["claims"][0]
    assert claim["sources"][0]["url"] == "https://reuters.com/hormuz" and claim["grounding"] == "snapshotted" and claim["product"] == "profiles"
    assert irgc["provenance"]["sources"][0]["product"] == "corpus_index" and irgc["schema"] == "ohmega.view.entity/1"
    assert irgc["events"][0]["title"] == "Strait closed" and "timeline" not in irgc            # the timeline is documents and events merged by date; the API does that
    leader = views["entity/person/iran-leader"].body
    assert leader["relations"][0]["rel"] == "head_of_state" and leader["relations"][0]["direction"] == "in"


def test_series_carry_their_basis_and_unit_and_are_trimmed(tmp_path):
    ctx = context(tmp_path, with_corpus=True)
    ctx.corpus.db.execute("PRAGMA foreign_keys = OFF")
    from algent_backend.corpus.sink import Sink

    s = Sink(ctx.corpus.db, "instruments", "series:x", "2026-10-23T00:00:00+00:00")
    ctx.corpus.db.isolation_level = None
    for i in range(60):
        s.observation("chk_x", f"2026-08-{i % 28 + 1:02d}-{i}", float(i), entity="org:irgc", unit="ships", basis="our_count", label="Transits")
    out = entity.build_one(ctx, "org:irgc", 99).body["series"][0]
    assert out["basis"] == "our_count" and out["unit"] == "ships" and len(out["points"]) == flags.SERIES_POINTS and out["n"] == 60


def test_a_geoledger_place_view_carries_the_asset_its_history_and_the_theaters_that_put_it_there(tmp_path):
    asset = {"id": "plant1", "name": "Bandar Abbas power plant", "type": "power_plant", "country": "IR", "lat": 27.1, "lon": 56.2, "events": 1}
    event = {"id": "e1", "asset_id": "plant1", "occurred_on": "2026-10-21", "observed_at": "2026-10-22", "status": "damaged", "claimant": "Iran", "via": "daily:2026-10-21:thr_hormuz",
             "sources": ["https://example.org/x"]}
    ctx = context(tmp_path, with_corpus=True)
    ctx.tables._docs["geo/a/plant1.json"] = {"asset": asset, "events": [event]}
    v = views_by_key(ctx)["entity/place/plant1"].body
    assert v["place"]["asset"]["name"] == "Bandar Abbas power plant" and v["place"]["history"][0]["status"] == "damaged"
    assert v["place"]["theaters"] == [{"id": "thr_hormuz", "name": "Hormuz crisis", "direction": "rising", "band": "severe", "linked": True}]
    assert [s["product"] for s in v["provenance"]["sources"]] == ["corpus_index", "geoledger"]


def test_entity_keys_are_path_safe_and_stable():
    assert entity.entity_key("org:irgc", "org") == "entity/org/irgc"
    assert entity.entity_key("place:chokepoint:strait-of-hormuz", "place").startswith("entity/place/chokepoint_strait-of-hormuz-")
    assert entity.entity_key("person:José Müller", "person") == entity.entity_key("person:José Müller", "person") and "/" not in entity.entity_key("x:a/b", "org")[len("entity/org/"):]


def test_the_search_index_points_only_at_views_this_run_emits(tmp_path):
    ctx = context(tmp_path, with_corpus=True)
    res = build.build_all(ctx)
    assert not res.errors, res.errors
    keys = {v.key for v in res.views}
    idx = next(v.body for v in res.views if v.key == "search-index")
    assert idx["fields"]["entities"] == ["name", "kind", "key", "uses", "aliases"]
    rows = {r[0]: r for r in idx["entities"]}
    assert rows["Iran"][2] == "country/IR" and rows["IRGC"][2] == "entity/org/irgc" and "Revolutionary Guards" in rows["IRGC"][4]
    assert all(r[2] in keys for r in idx["entities"])
    assert idx["documents"][0][3] == "Hormuz closure"
    assert not [v for v in res.views if v.over_budget()]


def test_without_a_corpus_the_corpus_families_are_simply_absent(tmp_path):
    res = build.build_all(context(None), None)
    assert not res.errors and not [v for v in res.views if v.family in ("entity", "search-index")]
    iran = next(v.body for v in res.views if v.key == "country/IR")
    assert "relations" not in iran and "series" not in iran and iran["panel"]["stats"]
    assert country.corpus_block(context(None), "IR") == {}


def test_country_view_gains_relations_and_series_with_a_corpus(tmp_path):
    ctx = context(tmp_path, with_corpus=True)
    iran = next(v.body for v in country.build(ctx) if v.key == "country/IR")
    assert iran["series"][0]["metric"] == "gdp" and iran["series"][0]["basis"] == "official" and iran["series"][0]["points"][-1] == ["2024", 4e11]
    assert iran["relations"][0]["rel"] == "head_of_state" and iran["about"]["documents"] == 1
