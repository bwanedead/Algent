"""Geoledger extraction: the wire schema, grounding against the material, resolution to assets, read-once memory, the
daily step, the hand-written event path, and the backfill plan (all with a fake model, offline)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from algent_backend.geoledger import backfill, flags, ingest
from algent_backend.geoledger import extract as ex
from algent_backend.geoledger.contracts import Asset
from algent_backend.geoledger.materials import Item, Material, from_document, from_profile, from_section
from algent_backend.geoledger.store import Ledger

TODAY = date(2026, 10, 14)
MOD = "https://mil.example/mod-2026-10-03"
UKR = "https://energy.example/ukrenergo-2026-10-04"


def _section() -> dict:
    return {"theater_id": "thr_ua", "name": "Ukraine war", "developments": [
        {"headline": "Russia says it struck Ukrainian power plants",
         "detail": "Russia's defence ministry said it hit the Darnytska CHP-4, Trypillya TPP and Zmiivska TPP overnight.",
         "when": "2026-10-03", "statements": [], "sources": [MOD]},
        {"headline": "Ukraine reports damage at Trypillya",
         "detail": "Ukrenergo said equipment at the Trypillya thermal plant was damaged and repairs would take weeks.",
         "when": "2026-10-04", "statements": [], "sources": [UKR]}]}


def _cand(**kw) -> ex.CandidateEvent:
    base = dict(item_ids=["d1"], name_as_written="Zmiivska TPP", type="power_plant", country="UA", status="claimed_struck",
                claimant="Russian Ministry of Defence", date="2026-10-03", quote="said it hit the Darnytska CHP-4", confidence="medium")
    return ex.CandidateEvent(**{**base, **kw})


def _fleet(tmp_path) -> Ledger:
    led = Ledger(tmp_path)
    led.add_assets([Asset(id="wri-z", name="Zmiyivska", type="power_plant", country="UA", lat=49.58, lon=36.52),
                    Asset(id="wri-t", name="Trypilska", type="power_plant", country="UA", lat=50.13, lon=30.74)])
    return led


def _ask(events: list[ex.CandidateEvent]):
    calls: list[str] = []

    def ask(schema, role, task):
        calls.append(task)
        assert schema is ex.CandidatePlan
        return ex.CandidatePlan(events=events)
    ask.calls = calls                                                         # type: ignore[attr-defined]
    return ask


def _has_union(node) -> bool:
    if isinstance(node, dict):
        return any(k in ("oneOf", "anyOf", "allOf") or _has_union(v) for k, v in node.items())
    return isinstance(node, list) and any(_has_union(v) for v in node)


def test_the_wire_schema_has_no_unions() -> None:
    assert not _has_union(ex.CandidatePlan.model_json_schema())


# -- grounding -----------------------------------------------------------------------------------

def test_sources_and_dates_come_from_the_cited_items_never_from_the_model() -> None:
    m = from_section(_section(), "2026-10-14")
    cands, notes = ex.validate(ex.CandidatePlan(events=[_cand(date="")]), m, today=TODAY)
    assert notes == [] and cands[0].sources == [MOD] and cands[0].occurred_on == "2026-10-03"        # the item's own day
    assert cands[0].note == "said it hit the Darnytska CHP-4"


def test_a_candidate_must_cite_items_name_itself_in_them_and_have_a_source() -> None:
    m = from_section(_section(), "2026-10-14")
    plan = ex.CandidatePlan(events=[_cand(item_ids=["d9"]), _cand(name_as_written="Burshtyn TPP"),
                                    _cand(name_as_written="Zmiivska TPP", item_ids=["d1"])])
    cands, notes = ex.validate(plan, m, today=TODAY)
    assert len(cands) == 1 and len(notes) == 2 and "cites no item" in notes[0] and "name is not in the items" in notes[1]
    bare = Material("x", "x", "2026-10-14", (Item("d1", "Zmiivska TPP was hit.", (), "2026-10-03"),))
    assert ex.validate(ex.CandidatePlan(events=[_cand()]), bare, today=TODAY)[0] == []             # no source url in the item


def test_a_claimant_the_text_does_not_bear_out_is_replaced_by_the_outlet() -> None:
    m = from_section(_section(), "2026-10-14")
    cands, notes = ex.validate(ex.CandidatePlan(events=[_cand(claimant="Pentagon"), _cand(claimant="Russia's defence ministry")]), m, today=TODAY)
    assert cands[0].claimant == "reported via mil.example" and "not in the text" in notes[0]
    assert cands[1].claimant == "Russia's defence ministry"


def test_dates_outside_a_plausible_window_fall_back_and_positions_must_agree_with_the_country() -> None:
    m = from_section(_section(), "2026-10-14")
    far = _cand(date="2031-01-01", located=True, lat=49.58, lon=36.52)
    cands, _ = ex.validate(ex.CandidatePlan(events=[far]), m, today=TODAY, iso_at=lambda la, lo: "UA")
    assert cands[0].occurred_on == "2026-10-03" and (cands[0].lat, cands[0].lon) == (49.58, 36.52)
    cands, notes = ex.validate(ex.CandidatePlan(events=[far]), m, today=TODAY, iso_at=lambda la, lo: "RU")
    assert cands[0].lat is None and any("is in RU, not UA" in n for n in notes)


# -- resolution and the ledger -------------------------------------------------------------------

def test_candidates_match_existing_assets_or_mint_unplaced_ones_and_claims_stay_claims(tmp_path) -> None:
    led = _fleet(tmp_path)
    plan = [_cand(), _cand(name_as_written="Darnytska CHP-4", known_as="Kyiv CHP-4", place="Kyiv"),
            _cand(name_as_written="Trypillya TPP")]
    r = ingest.ingest(led, from_section(_section(), "2026-10-14"), _ask(plan), today=TODAY)
    assert r["error"] == "" and r["candidates"] == 3 and r["events"] == 3 and r["created"] == 1
    assert led.status("wri-z").status == "claimed_struck" and led.status("wri-z").claimant == "Russian Ministry of Defence"
    assert "Zmiivska TPP" in led.assets["wri-z"].aliases                               # the new spelling is remembered
    minted = led.assets["og-ua-power_plant-kyiv-chp-4"]
    assert (minted.precision, minted.lat, minted.provenance) == ("unplaced", None, "ohmega_derived") and minted.aliases == ["Darnytska CHP-4"]
    assert r["rows"][0]["asset_id"] == "wri-z" and r["rows"][0]["status"] == "claimed_struck"


def test_a_second_party_confirming_is_a_second_event_and_never_overwrites_the_claim(tmp_path) -> None:
    led = _fleet(tmp_path)
    ingest.ingest(led, from_section(_section(), "2026-10-14"), _ask([_cand(name_as_written="Trypillya TPP")]), today=TODAY)
    follow = [_cand(item_ids=["d2"], name_as_written="Trypillya thermal plant", status="reported_damaged", claimant="Ukrenergo",
                    date="2026-10-04", quote="equipment at the Trypillya thermal plant was damaged")]
    ingest.ingest(led, Material("Daily 2", "daily:2026-10-15:thr_ua", "2026-10-15", from_section(_section(), "x").items[1:]), _ask(follow), today=TODAY)
    assert [(e.status, e.claimant) for e in led.history("wri-t")] == [("claimed_struck", "Russian Ministry of Defence"), ("reported_damaged", "Ukrenergo")]
    assert led.status("wri-t").status == "reported_damaged"


def test_a_text_is_read_once_ever_and_a_failed_call_is_retried(tmp_path) -> None:
    led = _fleet(tmp_path)
    m = from_section(_section(), "2026-10-14")
    ask = _ask([_cand()])
    assert ingest.ingest(led, m, ask, today=TODAY)["events"] == 1
    again = ingest.ingest(led, m, ask, today=TODAY)
    assert again["skipped"] == "already read" and len(ask.calls) == 1 and again["rows"][0]["asset_id"] == "wri-z"   # rows rebuilt, no call

    def boom(*_a):
        raise RuntimeError("provider 400")
    other = Material("y", "daily:2026-10-14:other", "2026-10-14", m.items)
    failed = ingest.ingest(led, other, boom, today=TODAY)
    assert "RuntimeError" in failed["error"] and failed["events"] == 0
    assert ingest.ingest(led, other, _ask([_cand()]), today=TODAY)["error"] == ""                              # not marked read: retried


# -- the daily's step ----------------------------------------------------------------------------

def test_attach_sets_the_sections_asset_events_and_never_raises(tmp_path) -> None:
    led = _fleet(tmp_path)
    sections = [_section()]
    report = ingest.attach(sections, ask=_ask([_cand(), _cand(item_ids=["d2"], name_as_written="Trypillya thermal plant", status="reported_damaged",
                                                           claimant="Ukrenergo", date="2026-10-04", quote="")]),
                           as_of="2026-10-14", ledger=led, publish_now=False)
    assert report["events"] == 2 and report["errors"] == []
    assert [r["status"] for r in sections[0]["asset_events"]] == ["claimed_struck", "reported_damaged"]
    assert sections[0]["asset_events"][0]["sources"] == [MOD] and sections[0]["asset_events"][0]["claimant"]

    def boom(*_a):
        raise RuntimeError("down")
    s2 = [_section()]
    r2 = ingest.attach(s2, ask=boom, as_of="2026-10-13", ledger=_fleet(tmp_path / "b"), publish_now=False)
    assert r2["errors"] and "asset_events" not in s2[0]


def test_attach_is_off_when_the_flag_is_off(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(flags, "ENABLED", False)
    assert ingest.attach([_section()], ask=_ask([]), as_of="2026-10-14", ledger=_fleet(tmp_path)) is None


# -- the hand-written path -----------------------------------------------------------------------

def test_add_event_requires_a_dated_sourced_claimant(tmp_path) -> None:
    led = _fleet(tmp_path)
    kw = dict(status="confirmed_damaged", claimant="Ukrenergo", occurred_on="2026-10-05", sources=[UKR])
    e = ingest.add_event(led, "wri-z", **kw)
    assert led.status("wri-z").id == e.id and e.provenance == "aggregated"
    assert ingest.add_event(led, "wri-z", **{**kw, "claimant": "Ohmega analysis", "occurred_on": "2026-10-06"}).provenance == "ohmega_derived"
    for bad in ({"claimant": " "}, {"occurred_on": "5 Oct"}, {"sources": ["not a url"]}, {"status": "mostly_fine"}, {"confidence": "sure"}):
        with pytest.raises(ValueError):
            ingest.add_event(led, "wri-z", **{**kw, **bad})
    with pytest.raises(ValueError):
        ingest.add_event(led, "nope", **kw)


# -- materials and backfill ----------------------------------------------------------------------

def test_materials_carry_the_sources_of_what_they_were_made_from() -> None:
    prof = {"id": "prof_1", "title": "Grid strikes", "as_of": "2026-10-05", "source_ledger": [{"id": "s1", "url": "https://a.example/x"}],
            "claim_ledger": [{"id": "c1", "text": "Ukrenergo reported damage at Trypillya.", "supported_by": ["s1"]}]}
    m = from_profile(prof)
    assert m.via == "profile:prof_1" and m.items[0].urls == ("https://a.example/x",) and m.items[0].when == "2026-10-05"
    doc = from_document("https://b.example/y", "T", "para one\n\n" + "word " * 700 + "\n\nlast", "2026-10-02")
    assert len(doc.items) >= 2 and all(i.urls == ("https://b.example/y",) for i in doc.items)
    assert from_section(_section(), "2026-10-14").key == from_section(_section(), "2026-10-14").key


def test_large_materials_are_read_in_batches() -> None:
    items = tuple(Item(f"a{k}", "x" * 4000, ("https://b.example",)) for k in range(5))
    assert [len(b.items) for b in Material("t", "v", "2026-10-14", items).batches()] == [2, 2, 1]


def test_worth_reading_gates_spend_only(monkeypatch) -> None:
    assert backfill.worth_reading("Drones struck the Kremenchuk oil refinery overnight")
    assert not backfill.worth_reading("Talks about talks continue in Geneva")


def test_backfill_reads_saved_dailies_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))
    d = tmp_path / "intel" / "daily" / "geopolitics"
    d.mkdir(parents=True)
    (d / "2026-10-05.json").write_text(json.dumps({"theaters": [_section()]}), encoding="utf-8")
    (d / "2026-08-01.json").write_text(json.dumps({"theaters": [_section()]}), encoding="utf-8")        # outside the window
    led = _fleet(tmp_path / "led")
    assert len(backfill.plan("2026-09-14", ("daily",), led)) == 1
    ask = _ask([_cand()])
    out = backfill.run(led, ask, "2026-09-14", ("daily",))
    assert out["materials"] == 1 and out["events"] == 1 and out["by_kind"] == {"daily": 1}
    assert backfill.plan("2026-09-14", ("daily",), led) == []                                           # nothing left to pay for
    assert backfill.run(led, ask, "2026-09-14", ("daily",))["materials"] == 0 and len(ask.calls) == 1
