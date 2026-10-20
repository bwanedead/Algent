"""Honest numbers: the percentile window, speaker spellings folded to one person, the record export's real total, and the live
provenance block the site's stats registry reads. Offline."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from algent_backend.agent_system.agents.intel import on_record
from algent_backend.agent_system.agents.statements import speakers
from algent_backend.agent_system.agents.statements import store as sstore
from algent_backend.instruments import moves
from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import Observation
from algent_backend.live import provenance
from algent_backend.live.memory import flags as memory_flags
from algent_backend.live.regions import GATES
from tests.test_intel_sensing import _st

TODAY = date(2026, 10, 20)


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path / "sstore"))


def _series(n: int, start: date = date(2025, 1, 1)):
    return [(start + timedelta(days=i), float(i + 1)) for i in range(n)]


# ── percentile window ─────────────────────────────────────────────────────────────────────────
def test_percentile_1y_needs_a_real_year_of_history() -> None:
    young = moves.compute(_series(9), today=date(2025, 1, 9))
    assert young["percentile_1y"] is None
    assert young["history_days"] == 8 and young["history_since"] == "2025-01-01"
    assert young["percentile_window"] == {"value": young["percentile_window"]["value"], "days": 8, "n": 9}
    assert young["percentile_window"]["value"] > 90                      # still ranked, but under its true window


def test_percentile_1y_is_published_once_the_history_spans_a_year() -> None:
    old = moves.compute(_series(400), today=date(2026, 2, 5))
    assert old["percentile_1y"] is not None and old["percentile_1y"] > 99
    assert old["percentile_window"]["days"] == 365 and old["history_days"] == 399


# ── speaker spellings ─────────────────────────────────────────────────────────────────────────
def _speakers(names: list[tuple[str, str]]):
    return [_st(n, "2026-10-01", f"remark {i}", affiliation=aff) for i, (n, aff) in enumerate(names)]


def test_spellings_of_one_person_fold_to_the_commonest() -> None:
    rows = _speakers([("Volodymyr Zelensky", "Ukraine")] * 1) + [_st("Volodymyr Zelensky", "2026-10-02", "b", affiliation="Ukraine"),
                                                              _st("Zelenskyy", "2026-10-03", "c", affiliation="Ukraine"),
                                                              _st("Seyed Abbas Araghchi", "2026-10-03", "d", affiliation="Iran"),
                                                              _st("Abbas Araghchi", "2026-10-03", "e", affiliation="Iran"),
                                                              _st("Abbas Araghchi", "2026-10-04", "f", affiliation="Iran"),
                                                              _st("Donald J. Trump", "2026-10-03", "g", affiliation="United States"),
                                                              _st("Donald Trump", "2026-10-03", "h", affiliation="United States"),
                                                              _st("Donald Trump", "2026-10-04", "i", affiliation="United States")]
    m = speakers.canonical_map(rows)
    assert m == {"Zelenskyy": "Volodymyr Zelensky", "Seyed Abbas Araghchi": "Abbas Araghchi", "Donald J. Trump": "Donald Trump"}


def test_different_people_and_ambiguous_surnames_are_not_merged() -> None:
    rows = [_st("Ali Khamenei", "2026-10-01", "a", affiliation="Iran"), _st("Mojtaba Khamenei", "2026-10-01", "b", affiliation="Iran"),
            _st("Khamenei", "2026-10-01", "c", affiliation="Iran"),
            _st("Donald Trump", "2026-10-01", "d", affiliation="United States"), _st("Melania Trump", "2026-10-01", "e", affiliation="United States"),
            _st("Kremlin", "2026-10-01", "f", affiliation="Russia"), _st("Kremlin spokesperson Dmitry Peskov", "2026-10-01", "g", affiliation="Russia"),
            _st("Trump", "2026-10-01", "h", affiliation="Russia")]
    assert speakers.canonical_map(rows) == {}


def test_same_surname_under_another_affiliation_is_left_alone() -> None:
    rows = [_st("Kim Jong Un", "2026-10-01", "a", affiliation="North Korea"), _st("Kim", "2026-10-01", "b", affiliation="South Korea")]
    assert speakers.canonical_map(rows) == {}


# ── record export totals ──────────────────────────────────────────────────────────────────────
def test_export_reports_real_total_cap_and_collection_start(monkeypatch) -> None:
    monkeypatch.setattr(on_record, "MAX_STATEMENTS", 3)
    sstore.append_statements([_st(f"Speaker{i}", (TODAY - timedelta(days=i)).isoformat(), f"unique remark number {i} about {'x' * i}", affiliation=f"Country{i}")
                              for i in range(5)])
    sstore.append_statements([_st("Old Speaker", (TODAY - timedelta(days=90)).isoformat(), "ancient remark", affiliation="Oldland")])
    out = on_record.export(today=TODAY)
    assert (out["count"], out["total"], out["capped"]) == (3, 5, True)
    assert out["collecting_since"] == (TODAY - timedelta(days=90)).isoformat() and out["basis"] == "model_extracted"


def test_export_folds_speaker_spellings() -> None:
    sstore.append_statements([_st("Volodymyr Zelensky", "2026-10-19", "first words", affiliation="Ukraine"),
                              _st("Volodymyr Zelensky", "2026-10-18", "second words here", affiliation="Ukraine"),
                              _st("Zelenskyy", "2026-10-17", "third and other words", affiliation="Ukraine")])
    rows = on_record.export(today=TODAY)["statements"]
    assert {r["speaker"] for r in rows} == {"Volodymyr Zelensky"}
    assert [r.get("speaker_as_said") for r in rows if r.get("speaker_as_said")] == ["Zelenskyy"]


# ── live provenance ───────────────────────────────────────────────────────────────────────────
def test_live_provenance_reads_since_from_the_store() -> None:
    sid = f"live_ais_{GATES[0].slug}_transits"
    istore.append(sid, [Observation(series_id=sid, period=(TODAY - timedelta(days=d)).isoformat(), value=1.0, fetched_at="t", source_url="u")
                        for d in (9, 8, 1)])
    p = provenance.build(TODAY)
    assert p["ships"]["basis"] == "our_count" and p["ships"]["since"] == (TODAY - timedelta(days=9)).isoformat() and p["ships"]["history_days"] == 9
    assert p["fires"]["since"] == "" and p["aircraft"]["basis"] == "our_derived"
    assert p["min_history_days"] == memory_flags.MIN_WEEKS * 7
