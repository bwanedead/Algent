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
                  "recent_share": 0.25, "prior_share": 0.05,
                  "first_seen": "2026-09-20", "series": [{"day": "2026-09-29", "count": 5, "editions": 2}]},
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
    assert snap["theaters"][0]["recent_share"] == 0.25 and snap["theaters"][0]["series"][0]["editions"] == 2
    assert snap["theaters"][1]["prior_share"] == 0.0
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


def test_pick_theaters_filters_by_domain() -> None:
    board = {"theaters": [{"id": "a", "domain": "geopolitics"}, {"id": "b", "domain": "Politics"},
                          {"id": "c", "domain": "technology"}],
             "heat": [{"theater_id": "c", "heat": 9, "trend": "steady"}, {"theater_id": "a", "heat": 5, "trend": "steady"},
                      {"theater_id": "b", "heat": 3, "trend": "steady"}]}
    assert desk.pick_theaters(board, 5) == ["c", "a", "b"]
    assert desk.pick_theaters(board, 5, []) == ["c", "a", "b"]
    assert desk.pick_theaters(board, 5, ["geopolitics", " POLITICS"]) == ["a", "b"]
    assert desk.pick_theaters(board, 1, ["politics"]) == ["b"]
    assert desk.pick_theaters(board, 5, ["science"]) == []


def test_pick_theaters_prefers_heating_on_ties() -> None:
    board = {"heat": [{"theater_id": "a", "heat": 5, "trend": "steady"}, {"theater_id": "b", "heat": 5, "trend": "new"},
                      {"theater_id": "c", "heat": 9, "trend": "cooling"}]}
    assert desk.pick_theaters(board, 2) == ["c", "b"]


def test_write_intel_writes_the_agent_feed(tmp_path) -> None:
    intel, store = _intel_dir(tmp_path), _store(tmp_path)
    snap = intel_page.build_snapshot(store, intel, now=NOW)
    site = tmp_path / "site"
    intel_page.write_intel(site, snap, intel, store)
    feed = json.loads((site / "public" / "data" / "pulses.json").read_text(encoding="utf-8"))
    assert feed["schema"] == "ohmega.pulses/1" and feed["built_at"] == NOW.isoformat()
    by = {p["id"]: p for p in feed["pulses"]}
    assert "pls_old" not in by and set(by["pls_a_hi"]) >= {"situation", "question", "status", "history", "rationale"}
    assert by["pls_a_hi"]["rationale"] == "Strikes rose and held." and "absolute_position" not in json.dumps(feed)
    index = json.loads((site / "public" / "data" / "intel.json").read_text(encoding="utf-8"))
    assert index["schema"] == "ohmega.intel.index/1"
    assert index["briefs"][0]["url"] == "/intel/briefs/2026-09-29-one"
    assert index["theaters"][0]["brief_url"] == "/intel/briefs/2026-09-29-one" and index["theaters"][1]["brief_url"] is None
    assert "scorecard" not in index and "resolved" in index["forecast_scorecard"]
    intel_page.write_intel(tmp_path / "bare", snap, intel)                       # no store: no pulses.json
    assert not (tmp_path / "bare" / "public" / "data" / "pulses.json").exists()


# ── the full agent feed ───────────────────────────────────────────────────────────────────────
def _feed_fixture(tmp_path):
    from algent_backend.agent_system.agents.intel import forecasts
    from algent_backend.agent_system.agents.intel.contracts import Judgment

    intel, store = _intel_dir(tmp_path), _store(tmp_path)
    for date, built in (("2026-09-28", "2026-09-28T07:00:00+00:00"), ("2026-09-29", "2026-09-29T07:00:00+00:00")):
        folder = intel / "daily" / "geopolitics"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{date}.json").write_text(json.dumps({
            "schema": "ohmega.daily/1", "domain": "geopolitics", "date": date, "built_at": built,
            "summary": {"headline": f"H {date}", "the_day": []}, "theaters": [],
            "pulse_proposals": [{"theater": "One", "name": "internal"}]}), encoding="utf-8")
    brief = intel / "briefs" / "2026-09-29-one.json"
    rec = json.loads(brief.read_text(encoding="utf-8"))
    rec["judgments"] = [{"statement": "X happens", "probability": 70, "horizon": "2026-10-10"}]
    brief.write_text(json.dumps(rec), encoding="utf-8")
    forecasts.record("2026-09-29-one", "thr_1",
                     [Judgment(statement="X happens", probability=70, horizon="2026-10-10"),
                      Judgment(statement="Y happens", probability=30, horizon="2026-10-12")],
                     made_at="2026-09-29T10:00:00+00:00", root=intel)
    forecasts.resolve(forecasts.forecast_id("2026-09-29-one", "Y happens"), "no", "it did not",
                      at="2026-09-30T09:00:00+00:00", root=intel)
    for pid, at, mode, pos, decision, slug in (
            ("pls_a_hi", "2026-09-30T08:00:00+00:00", "blind", 55, "no_change", ""),
            ("pls_a_hi", "2026-09-30T09:00:00+00:00", "article", 60, "applied", "the-slug"),
            ("pls_a_hi", "2026-08-01T09:00:00+00:00", "reassess", 10, "applied", "")):   # outside the window
        store.append(Influence(pulse_id=pid, at=at, mode=mode, definition_version=1, proposed_position=pos,
                               absolute_position=77, decision=decision, rationale="Why [clm_ab12] so.",
                               key=f"k_{at}_{mode}", model="m-1", prompt_version="secret-v9",
                               source={"article_slug": slug, "profile_id": "prof_1", "claim_ids": ["clm_ab12"]}))
    return intel, store


def test_agent_feed_files_and_no_internal_fields(tmp_path) -> None:
    intel, store = _feed_fixture(tmp_path)
    site = tmp_path / "site"
    intel_page.write_intel(site, intel_page.build_snapshot(store, intel, now=NOW), intel, store)
    data = site / "public" / "data"
    load = lambda rel: json.loads((data / rel).read_text(encoding="utf-8"))  # noqa: E731
    daily = load("daily/geopolitics/2026-09-29.json")
    assert "pulse_proposals" not in daily and daily["url"] == "/geopolitics/2026-09-29"
    assert daily["data_url"] == "/data/daily/geopolitics/2026-09-29.json"
    assert load("daily/geopolitics/latest.json") == daily
    brief = load("briefs/2026-09-29-one.json")
    assert brief["url"] == "/intel/briefs/2026-09-29-one" and brief["judgments"][0]["id"].startswith("fc_")
    fc = load("forecasts.json")
    assert fc["schema"] == "ohmega.forecasts/1" and fc["scorecard"]["resolved"] == 1
    by = {f["statement"]: f for f in fc["forecasts"]}
    assert by["X happens"]["id"] == brief["judgments"][0]["id"] and by["X happens"]["resolution"] is None
    assert by["Y happens"]["status"] == "no" and by["Y happens"]["resolution"]["evidence"] == "it did not"
    assert by["X happens"]["brief_url"] == "/intel/briefs/2026-09-29-one" and by["X happens"]["theater"] == "One"
    pulse = load("pulses/pls_a_hi.json")
    assert pulse["schema"] == "ohmega.pulse/1" and pulse["definition"]["question"] == "q pls_a_hi"
    assert [r["mode"] for r in pulse["readings"]] == ["reassessment", "article", "audit", "article"]   # oldest first
    audit, article = pulse["readings"][2], pulse["readings"][3]
    assert audit["moves_pulse"] is False and article["moves_pulse"] is True
    assert article["article_url"] == "/articles/the-slug" and audit["article_url"] is None
    assert article["rationale"] == "Why so." and article["model"] == "m-1"
    assert load("pulses.json")["pulses"][0]["data_url"].startswith("/data/pulses/")
    index = load("intel.json")
    assert index["daily"][0]["data_url"] == "/data/daily/geopolitics/2026-09-29.json"
    assert index["briefs"][0]["data_url"] == "/data/briefs/2026-09-29-one.json"
    assert index["changes_url"] == "/data/changes.json"
    for path in data.rglob("*.json"):                                          # nothing internal anywhere
        text = path.read_text(encoding="utf-8")
        assert "absolute_position" not in text and "clm_" not in text and "secret-v9" not in text, path
        assert "prof_1" not in text and "pulse_proposals" not in text, path


def test_changes_feed_is_newest_first_and_windowed(tmp_path) -> None:
    intel, store = _feed_fixture(tmp_path)
    feed = intel_page.build_agent_files(intel_page.build_snapshot(store, intel, now=NOW), intel, store)["changes.json"]
    assert feed["schema"] == "ohmega.changes/1" and feed["window_days"] == 30
    ats = [e["at"] for e in feed["events"]]
    assert ats == sorted(ats, reverse=True) and feed["as_of"] == ats[0]
    assert not any(e["at"].startswith("2026-08-01") for e in feed["events"])      # older than 30 days
    kinds = {e["type"] for e in feed["events"]}
    assert kinds == {"pulse_created", "pulse_moved", "brief_published", "daily_published",
                     "forecast_made", "forecast_resolved"}
    moved = next(e for e in feed["events"] if e["type"] == "pulse_moved" and e["pulse_id"] == "pls_a_hi")
    assert (moved["from"], moved["to"], moved["band_changed"]) == (40, 60, True)
    assert moved["url"] == "/pulses" and moved["data_url"] == "/data/pulses/pls_a_hi.json"
    later = intel_page.build_agent_files(
        intel_page.build_snapshot(store, intel, now=datetime(2026, 11, 15, tzinfo=UTC)), intel, store)["changes.json"]
    assert later["events"] == [] and later["as_of"] == ""


def test_agent_feed_rewrites_only_what_changed(tmp_path) -> None:
    intel, store = _feed_fixture(tmp_path)
    site = tmp_path / "site"
    intel_page.write_intel(site, intel_page.build_snapshot(store, intel, now=NOW), intel, store)
    data = site / "public" / "data"
    stamps = {p: p.stat().st_mtime_ns for p in data.rglob("*.json")}
    later = datetime(2026, 9, 30, 14, 6, tzinfo=UTC)
    intel_page.write_intel(site, intel_page.build_snapshot(store, intel, now=later), intel, store)
    changed = {p.name for p, t in stamps.items() if p.stat().st_mtime_ns != t}
    assert changed <= {"intel.json", "pulses.json"}                              # only the built_at-stamped ones
    no_store = tmp_path / "bare"
    intel_page.write_intel(no_store, intel_page.build_snapshot(store, intel, now=NOW), intel)
    assert not (no_store / "public" / "data" / "changes.json").exists()
    assert (no_store / "public" / "data" / "forecasts.json").exists()
