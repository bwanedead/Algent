"""The intel desk's durable briefs and the site snapshot — no network, no model."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from algent_backend.agent_system.agents.intel import desk
from algent_backend.agent_system.agents.intel.contracts import Brief, Escalation, Theater
from algent_backend.agent_system.agents.pulse import PulseStore
from algent_backend.agent_system.agents.pulse.contracts import (
    Influence,
    Pulse,
    PulseDefinition,
    Situation,
    Watch,
)
from algent_backend.publishing import intel_page

NOW = datetime(2026, 9, 30, 14, 5, tzinfo=UTC)


def _pulse(store: PulseStore, sit: str, pid: str, *, position: float | None, rationale: str = "r",
           status: str = "active") -> None:
    store.create_pulse(Pulse(id=pid, situation_id=sit, name=pid, status=status,
                             definitions=[PulseDefinition(question=f"q {pid}", low_end="lo", high_end="hi")]))
    if position is not None:
        store.append(Influence(pulse_id=pid, at="2026-09-29T10:00:00+00:00", mode="article", definition_version=1,
                               proposed_position=position, absolute_position=99, decision="applied",
                               rationale=rationale, key=f"k_{pid}"))


def _store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "pulses")
    for sid, title, status in (("sit_a", "A", "active"), ("sit_b", "B", "active"), ("sit_c", "C", "active"),
                               ("sit_old", "Old", "merged")):
        store.save_situation(Situation(id=sid, title=title, status=status))
    _pulse(store, "sit_a", "pls_a_low", position=20)
    _pulse(store, "sit_a", "pls_a_none", position=None)
    _pulse(store, "sit_a", "pls_a_hi", position=40, rationale="Strikes rose [clm_ab12, clm_cd34] and (clm_ef56) held.")
    _pulse(store, "sit_b", "pls_b", position=80)
    _pulse(store, "sit_b", "pls_b_dormant", position=95, status="dormant")
    _pulse(store, "sit_c", "pls_c", position=None)
    _pulse(store, "sit_old", "pls_old", position=99)
    store.save_watch(Watch(id="w1", situation_id="sit_b", condition="open one", expected_direction="up"))
    store.save_watch(Watch(id="w2", situation_id="sit_b", condition="done", status="expired"))
    return store


def _intel_dir(tmp_path):
    d = tmp_path / "intel"
    (d / "boards").mkdir(parents=True)
    (d / "boards" / "2026-09-29.json").write_text(json.dumps({
        "as_of": "2026-09-29",
        "theaters": [{"id": "thr_1", "name": "One", "domain": "geopolitics", "why": "because", "members": []},
                     {"id": "thr_2", "name": "Two", "members": []}],
        "heat": [{"theater_id": "thr_1", "name": "One", "heat": 9, "trend": "heating", "recent": 5, "prior": 1,
                  "first_seen": "2026-09-20", "series": [{"day": "2026-09-29", "count": 5}]},
                 {"theater_id": "thr_2", "name": "Two", "heat": 3, "trend": "steady", "recent": 1, "prior": 1}]}),
        encoding="utf-8")
    (d / "briefs").mkdir()
    for slug, as_of, built, tid in (("2026-09-27-one", "2026-09-27", "2026-09-27T10:00:00+00:00", "thr_1"),
                                    ("2026-09-29-one", "2026-09-29", "2026-09-29T10:00:00+00:00", "thr_1")):
        (d / "briefs" / f"{slug}.json").write_text(json.dumps({
            "schema": "ohmega.brief/1", "slug": slug, "as_of": as_of, "built_at": built, "theater_id": tid,
            "theater_name": "One", "title": f"T {slug}", "bottom_line": "bl",
            "escalation": {"direction": "rising", "pace": "fast"}}), encoding="utf-8")
    return d


def test_snapshot_orders_filters_and_cleans(tmp_path) -> None:
    snap = intel_page.build_snapshot(_store(tmp_path), _intel_dir(tmp_path), now=NOW)
    assert snap["schema"] == "ohmega.intel/1" and snap["slug"] == "2026-09-30-1405"
    assert [s["id"] for s in snap["situations"]] == ["sit_b", "sit_a", "sit_c"]   # merged skipped; unassessed last
    b, a, c = snap["situations"]
    assert [p["id"] for p in b["pulses"]] == ["pls_b"]                            # dormant skipped
    assert [w["condition"] for w in b["watches"]] == ["open one"]
    assert [p["id"] for p in a["pulses"]] == ["pls_a_hi", "pls_a_low", "pls_a_none"]
    assert a["pulses"][2]["band"] == "unassessed" and a["pulses"][2]["position"] is None
    assert "absolute_position" not in json.dumps(snap)
    assert a["pulses"][0]["rationale"] == "Strikes rose and held."
    assert c["pulses"][0]["band"] == "unassessed"


def test_reader_safe_trims_at_a_word() -> None:
    assert intel_page.reader_safe("Held [clm_1a]. See (clm_2b, clm_3c) now  ok") == "Held. See now ok"
    long = intel_page.reader_safe("word " * 200)
    assert len(long) <= 402 and long.endswith("…") and "wor…" not in long


def test_theaters_link_to_newest_brief_and_briefs_are_newest_first(tmp_path) -> None:
    snap = intel_page.build_snapshot(_store(tmp_path), _intel_dir(tmp_path), now=NOW)
    assert [t["id"] for t in snap["theaters"]] == ["thr_1", "thr_2"]
    assert snap["theaters"][0]["brief"] == "2026-09-29-one" and snap["theaters"][1]["brief"] is None
    assert [b["slug"] for b in snap["briefs"]] == ["2026-09-29-one", "2026-09-27-one"]
    assert snap["briefs"][0]["direction"] == "rising" and snap["briefs"][0]["pace"] == "fast"


def test_write_intel_writes_files_and_is_idempotent(tmp_path) -> None:
    intel = _intel_dir(tmp_path)
    snap = intel_page.build_snapshot(_store(tmp_path), intel, now=NOW)
    site = tmp_path / "site"
    path = intel_page.write_intel(site, snap, intel)
    assert path == site / "content" / "intel" / "snapshots" / "2026-09-30-1405.json"
    assert json.loads(path.read_text(encoding="utf-8"))["slug"] == snap["slug"]
    brief_files = sorted((site / "content" / "intel" / "briefs").glob("*.json"))
    assert [p.stem for p in brief_files] == ["2026-09-27-one", "2026-09-29-one"]
    stamps = {p: p.stat().st_mtime_ns for p in [path, *brief_files]}
    intel_page.write_intel(site, snap, intel)
    assert stamps == {p: p.stat().st_mtime_ns for p in stamps}                      # untouched


class _Model:
    def __init__(self, brief):
        self.brief = brief

    def with_structured_output(self, _s):
        return self

    def invoke(self, *_a, **_k):
        return self.brief


def test_produce_persists_a_durable_brief_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "store"))
    brief = Brief(title="T", bottom_line="bl", escalation=Escalation(direction="rising", pace="fast"))
    ctx = type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": _Model(brief)})()})()})()
    theater = Theater(id="thr_x", name="Russia vs Europe")
    row = desk.produce(ctx, theater, {"recent": 3}, as_of="2026-09-29", focus="who pays?")
    from algent_backend.agent_system.agents.intel.brief import focus_tag

    slug = f"2026-09-29-russia-vs-europe-{focus_tag('who pays?')}"
    assert row["slug"] == slug and row["researched"] is False
    rec = json.loads((tmp_path / "store" / "briefs" / f"{slug}.json").read_text(encoding="utf-8"))
    assert rec["schema"] == "ohmega.brief/1" and rec["theater_id"] == "thr_x" and rec["focus"] == "who pays?"
    assert rec["heat"] == {"recent": 3} and rec["bottom_line"] == "bl" and rec["built_at"]


def test_import_briefs_is_idempotent_and_matches_the_board(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "store"))
    (tmp_path / "store" / "boards").mkdir(parents=True)
    (tmp_path / "store" / "boards" / "2026-09-28.json").write_text(json.dumps({
        "theaters": [{"id": "thr_x", "name": "Russia vs Europe"}],
        "heat": [{"theater_id": "thr_x", "name": "Russia vs Europe", "heat": 4}]}), encoding="utf-8")
    runs = tmp_path / "runs" / "2026-09-28"
    runs.mkdir(parents=True)
    (runs / "brief_russia-vs-europe.json").write_text(Brief(title="T", bottom_line="b").model_dump_json(),
                                                      encoding="utf-8")
    first = desk.import_briefs(tmp_path / "runs")
    assert first["imported"] == ["2026-09-28-russia-vs-europe"]
    rec = json.loads((tmp_path / "store" / "briefs" / "2026-09-28-russia-vs-europe.json").read_text(encoding="utf-8"))
    assert rec["theater_id"] == "thr_x" and rec["heat"]["heat"] == 4 and rec["focus"] == ""
    assert desk.import_briefs(tmp_path / "runs")["imported"] == []


def test_pick_theaters_prefers_heating_on_ties() -> None:
    board = {"heat": [{"theater_id": "a", "heat": 5, "trend": "steady"}, {"theater_id": "b", "heat": 5, "trend": "new"},
                      {"theater_id": "c", "heat": 9, "trend": "cooling"}]}
    assert desk.pick_theaters(board, 2) == ["c", "b"]
