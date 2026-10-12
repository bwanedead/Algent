"""The daily's reader aids: the `saga` (big-picture anchor), `headline` carried through every part of the day, and the
plain-English glossary published with the numbers."""

from __future__ import annotations

import json

from algent_backend.actors.catalog import INDICATORS
from algent_backend.actors.plain import PLAIN as ACTOR_PLAIN
from algent_backend.agent_system.agents.intel import daily, daily_editions, daily_rerender, numbers, primers
from algent_backend.instruments.catalog import CATALOG

from test_intel_daily import AS_OF, SUMMARY, _board, _ctx, _draft, _store
from test_intel_daily_editions import SUMMARY_2, _board_2

SAGA = "Alpha and Bravo have been at odds over a sea lane since 2019. Most of the region oil passes through it."


def _day(tmp_path, monkeypatch, tasks=None) -> dict:
    _store(tmp_path, monkeypatch)
    ctx = _ctx({"Alpha": _draft(headline="Alpha struck a port.", saga=SAGA), "Bravo": _draft()}, SUMMARY, tasks)
    return daily.produce_daily(ctx, domain="geopolitics", top=5, model_spec=None, as_of=AS_OF, board=_board())["report"]


def test_fit_saga_holds_the_contract() -> None:
    assert daily.fit_saga("  One.   Two.  Three.  Four. ") == "One. Two. Three."            # at most three sentences
    assert daily.fit_saga("See https://x.example/a for more. It matters.") == "See for more. It matters."
    assert daily.fit_saga("word " * 200 + ".") == ""                                       # a history lesson is dropped, not clipped
    assert daily.fit_saga("") == "" and daily.fit_saga(None) == ""                         # a one-off event has no saga


def test_saga_is_published_and_a_one_off_stays_empty(tmp_path, monkeypatch) -> None:
    rec = _day(tmp_path, monkeypatch)
    by = {s["theater_id"]: s for s in rec["theaters"]}
    assert by["thr_a"]["saga"] == SAGA and by["thr_b"]["saga"] == ""


def test_the_stored_primer_reaches_the_writer_as_stable_background(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    folder = tmp_path / "intel" / "primers"
    folder.mkdir(parents=True)
    (folder / "thr_a.json").write_text(json.dumps({"theater_id": "thr_a", "text": "PRIMER TEXT", "built_at": "2026-09-28T00:00:00+00:00"}),
                                       encoding="utf-8")
    assert primers.load(tmp_path / "intel")["thr_a"]["text"] == "PRIMER TEXT"
    tasks: list[str] = []
    ctx = _ctx({"Alpha": _draft(), "Bravo": _draft()}, SUMMARY, tasks)
    daily.produce_daily(ctx, domain="geopolitics", top=5, model_spec=None, as_of=AS_OF, board=_board())
    alpha, bravo = (next(t for t in tasks if f"THEATER: {n}" in t) for n in ("Alpha", "Bravo"))
    assert "STABLE BACKGROUND" in alpha and "PRIMER TEXT" in alpha and "STABLE BACKGROUND" not in bravo


def test_rerender_carries_the_saga_and_headline_with_no_model(tmp_path, monkeypatch) -> None:
    _day(tmp_path, monkeypatch)
    monkeypatch.setattr(daily, "_ask", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no model")))
    rec = daily_rerender.rerender("geopolitics", AS_OF, countries=[])["report"]
    alpha = next(s for s in rec["theaters"] if s["theater_id"] == "thr_a")
    assert alpha["saga"] == SAGA and alpha["headline"] == "Alpha struck a port."


def test_headline_is_carried_by_part_two_updates_and_new_sections(tmp_path, monkeypatch) -> None:
    _day(tmp_path, monkeypatch)
    drafts = {"Alpha": _draft(headline="Alpha struck again this afternoon.", saga=""),
              "Delta": _draft(headline="Delta joined the dispute.", saga="Delta is new to the lane dispute.")}
    res = daily_editions.produce(_ctx(drafts, SUMMARY_2), domain="geopolitics", top=5, model_spec=None, as_of=AS_OF,
                                 board=_board_2())
    by = {s["theater_id"]: s for s in res["report"]["theaters"]}
    assert by["thr_a"]["updates"][0]["headline"] == "Alpha struck again this afternoon."
    assert by["thr_d"]["headline"] == "Delta joined the dispute." and by["thr_d"]["saga"].startswith("Delta")
    replay = daily_rerender.rerender("geopolitics", AS_OF, countries=[])["report"]
    alpha = next(s for s in replay["theaters"] if s["theater_id"] == "thr_a")
    assert alpha["updates"][0]["headline"] == "Alpha struck again this afternoon." and alpha["saga"] == SAGA


def test_every_series_and_opaque_actor_metric_has_a_plain_note() -> None:
    assert [s.id for s in CATALOG if len(s.plain.split()) < 6] == []
    assert all(s.plain.count(". ") <= 1 and s.plain.endswith(".") for s in CATALOG)          # <= 2 sentences
    assert set(ACTOR_PLAIN) <= {i.id for i in INDICATORS} | {"energy_production"}
    assert set(numbers.ACTOR_METRICS) - set(ACTOR_PLAIN) <= {"population", "oil_prod", "oil_cons", "gas_prod", "gas_cons",
                                                             "coal_prod", "coal_cons", "exports_pct", "imports_pct",
                                                             "exports_usd", "imports_usd"}


def test_a_tracker_publishes_its_plain_note() -> None:
    from datetime import date

    row = {"series_id": "px_ttf_gas", "name": "TTF", "unit": "EUR/MWh", "frequency": "daily", "source": "s", "source_url": "u",
           "public_display": False, "latest": {"value": 30.0, "period": AS_OF}, "age_days": 0, "changes": {}, "unusual": False,
           "unusual_reasons": [], "long_run_outside": False, "outside_note": "", "percentile_1y": None,
           "freshness": {"cadence": "daily", "status": "current", "note": ""}, "step_key": "prev", "step_label": "1d"}
    assert "Dutch" in numbers.tracker(row, date.fromisoformat(AS_OF))["plain"]
