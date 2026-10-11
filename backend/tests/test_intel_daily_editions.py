"""The daily's second part is an APPEND to one report: updates nest under the morning section, theaters the morning
did not cover get sections, nothing of part 1 is rewritten, and every part replays from its own drafts."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from algent_backend.agent_system.agents.intel import daily, daily_drafts, daily_editions, daily_rerender, flags, novelty
from algent_backend.agent_system.agents.intel.contracts import DaySummary, Member, Theater

from test_intel_daily import AS_OF, SRC_A, SRC_B, SUMMARY, _board, _ctx, _draft, _store

NEW_A = "https://wire.example/a2"
SUMMARY_2 = DaySummary(headline="Day so far: Alpha again, Delta new", the_day=["one", "two"])


def _board_2() -> dict:
    """The afternoon board: Alpha has one new headline, Bravo nothing, Delta is brand new."""
    board = _board()
    alpha = next(t for t in board["theaters"] if t["id"] == "thr_a")
    alpha["members"].append({"edition": "2026-09-29-1700", "n": 2, "title": "Alpha later", "thesis": "t", "sources": [NEW_A]})
    board["theaters"].append({"id": "thr_d", "name": "Delta", "domain": "geopolitics", "why": "w",
                              "members": [{"edition": "2026-09-29-1700", "n": 3, "title": "Delta headline", "thesis": "t",
                                           "sources": ["https://wire.example/d"]}]})
    board["heat"] = [
        {"theater_id": "thr_a", "name": "Alpha", "heat": 9.0, "trend": "heating", "state": "active",
         "novelty": {"since": "2026-09-28", "total": 5, "headlines": {"radar": 5}, "statements": 0, "instruments": 0}},
        {"theater_id": "thr_b", "name": "Bravo", "heat": 5.0, "trend": "steady", "state": "active",
         "novelty": {"since": "2026-09-28", "total": 4, "headlines": {"radar": 4}, "statements": 0, "instruments": 0}},
        {"theater_id": "thr_d", "name": "Delta", "heat": 3.0, "trend": "new", "state": "new",
         "novelty": {"since": "2026-09-22", "total": 1, "headlines": {"radar": 1}, "statements": 0, "instruments": 0}},
    ]
    return board


def _part_one(tmp_path, monkeypatch) -> dict:
    _store(tmp_path, monkeypatch)
    ctx = _ctx({"Alpha": _draft(bottom_line="MORNING alpha"), "Bravo": _draft(bottom_line="MORNING bravo")}, SUMMARY)
    return daily.produce_daily(ctx, domain="geopolitics", top=5, model_spec=None, as_of=AS_OF, board=_board())["report"]


def _part_two(tasks=None, **kw) -> dict:
    drafts = {"Alpha": _draft(bottom_line="AFTERNOON alpha"), "Delta": _draft(bottom_line="AFTERNOON delta")}
    return daily_editions.produce(_ctx(drafts, SUMMARY_2, tasks), domain="geopolitics", top=5, model_spec=None,
                                  as_of=AS_OF, board=_board_2(), **kw)


def test_part_one_records_its_edition(tmp_path, monkeypatch) -> None:
    rec = _part_one(tmp_path, monkeypatch)
    assert [e["n"] for e in rec["editions"]] == [1] and rec["editions"][0]["label"] == flags.edition_info(1).label
    assert {s["edition"] for s in rec["theaters"]} == {1}


def test_part_two_appends_updates_nested_and_new_sections_without_touching_part_one(tmp_path, monkeypatch) -> None:
    morning = _part_one(tmp_path, monkeypatch)
    tasks: list[str] = []
    res = _part_two(tasks)
    assert "error" not in res
    rec = json.loads((tmp_path / "intel" / "daily" / "geopolitics" / f"{AS_OF}.json").read_text(encoding="utf-8"))
    by = {s["theater_id"]: s for s in rec["theaters"]}
    # part 1's sections are what they were (Alpha gained only the nested update)
    for tid in ("thr_a", "thr_b"):
        assert {k: v for k, v in by[tid].items() if k != "updates"} == next(s for s in morning["theaters"] if s["theater_id"] == tid)
    assert [u["bottom_line"] for u in by["thr_a"]["updates"]] == ["AFTERNOON alpha"]
    assert by["thr_a"]["updates"][0]["kind"] == "update" and by["thr_a"]["updates"][0]["edition"] == 2
    assert "updates" not in by["thr_b"]                         # nothing new since the morning: not rewritten, not repeated
    assert by["thr_d"]["edition"] == 2 and by["thr_d"].get("kind") != "update"
    assert [t["theater_id"] for t in rec["theaters"]] == ["thr_a", "thr_b", "thr_d"]
    # one report: the day's summary is the unified one, editions keep provenance
    assert rec["summary"]["headline"] == SUMMARY_2.headline
    assert [e["n"] for e in rec["editions"]] == [1, 2]
    assert rec["editions"][0]["summary"]["headline"] == "Alpha heats up"
    assert {(s["theater_id"], s.get("update", False)) for s in rec["editions"][1]["sections"]} == {("thr_a", True), ("thr_d", False)}
    # the update was written against the morning section and told so; Bravo was never asked
    alpha_task = next(t for t in tasks if "THEATER: Alpha" in t)
    assert "THIS IS AN UPDATE" in alpha_task and "MORNING alpha" in alpha_task
    assert not any("THEATER: Bravo" in t for t in tasks)
    # the drafts are archived per part, so each replays on its own
    assert daily_drafts.editions_present("geopolitics", AS_OF) == [1, 2]
    assert set(daily_drafts.load("geopolitics", AS_OF, 2)["theaters"]) == {"thr_a", "thr_d"}
    assert set(daily_drafts.load("geopolitics", AS_OF, 1)["theaters"]) == {"thr_a", "thr_b"}


def test_a_part_is_never_built_twice_and_part_one_will_not_clobber_part_two(tmp_path, monkeypatch) -> None:
    _part_one(tmp_path, monkeypatch)
    _part_two()
    again = _part_two()
    assert "already exists" in again["error"] and again["report"] is None
    redo_one = daily.produce_daily(_ctx({}, SUMMARY), domain="geopolitics", top=5, model_spec=None, as_of=AS_OF,
                                   board=_board())
    assert "later parts" in redo_one["error"]


def test_a_quiet_afternoon_is_recorded_not_failed(tmp_path, monkeypatch) -> None:
    _part_one(tmp_path, monkeypatch)
    board = _board_2()
    board["heat"] = [h for h in board["heat"] if h["theater_id"] == "thr_b"]
    res = daily_editions.produce(_ctx({}, SUMMARY_2), domain="geopolitics", top=5, model_spec=None, as_of=AS_OF, board=board)
    assert "error" not in res
    rec = res["report"]
    assert [e["n"] for e in rec["editions"]] == [1, 2] and rec["editions"][1]["sections"] == []
    assert rec["summary"]["headline"] == "Alpha heats up"      # no additions: the day's top is kept


def test_part_two_without_part_one_is_a_whole_report(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    res = _part_two()
    assert "error" not in res and [e["n"] for e in res["report"]["editions"]] == [2]


def test_rerender_replays_each_part_from_its_own_drafts(tmp_path, monkeypatch) -> None:
    _part_one(tmp_path, monkeypatch)
    _part_two()
    res = daily_rerender.rerender("geopolitics", AS_OF)
    assert "error" not in res, res
    rec = res["report"]
    alpha = next(s for s in rec["theaters"] if s["theater_id"] == "thr_a")
    assert alpha["bottom_line"] == "MORNING alpha" and alpha["edition"] == 1
    assert [(u["bottom_line"], u["kind"], u["edition"]) for u in alpha["updates"]] == [("AFTERNOON alpha", "update", 2)]
    assert next(s for s in rec["theaters"] if s["theater_id"] == "thr_d")["edition"] == 2
    assert rec["summary"]["headline"] == SUMMARY_2.headline
    assert rec["editions"][0]["summary"]["headline"] == "Alpha heats up"


def test_novelty_since_seen_counts_only_what_the_earlier_part_was_not_shown() -> None:
    t = Theater(id="thr_x", name="X", members=[
        Member(edition="2026-09-29-0800", n=1, title="a", sources=[SRC_A]),
        Member(edition="2026-09-29-1700", n=2, title="b", sources=[NEW_A + "/"]),
        Member(edition="2026-09-29-1700", n=3, title="c", sources=[SRC_B])])
    nov = novelty.measure_since_seen(t, since="morning", as_of=date(2026, 9, 29), ev=None,
                                     seen_urls={SRC_A, SRC_B}, seen_statements=set(), seen_series=set())
    assert nov["total"] == 1 and nov["newest"] == "2026-09-29"


def test_next_edition_waits_for_its_time(tmp_path, monkeypatch) -> None:
    _part_one(tmp_path, monkeypatch)
    early, late = datetime(2026, 9, 29, 9, 0, tzinfo=UTC), datetime(2026, 9, 29, 18, 0, tzinfo=UTC)
    assert daily_editions.next_edition("geopolitics", AS_OF, early) == 1
    assert daily_editions.next_edition("geopolitics", AS_OF, late) == 2


def test_an_update_reuses_the_mornings_research_and_only_a_new_theater_is_researched(tmp_path, monkeypatch) -> None:
    from algent_backend.agent_system.agents.intel import brief as br
    from algent_backend.agent_system.agents.pulse import update as pulse_update
    from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile, SourceArtifact
    from algent_backend.agent_system.agents.research.store import JsonProfileStore

    _store(tmp_path, monkeypatch)
    monkeypatch.setattr(pulse_update, "update_quietly", lambda *a, **k: {})
    bought: list[str] = []
    monkeypatch.setattr(br, "commission_research", lambda _c, _cf, t, **k: bought.append(t.id))
    tag = AS_OF.replace("-", "")
    JsonProfileStore().save(SignalProfile(
        id=f"prof_intel_a_daily_{tag}", title="a", generated_at=f"{AS_OF}T05:00:00+00:00",
        source_ledger=[SourceArtifact(id="src_1", url="https://x.example/a")],
        claim_ledger=[Claim(id="clm_1", text="a claim", supported_by=["src_1"])]))
    daily.produce_daily(_ctx({"Alpha": _draft()}, SUMMARY), domain="geopolitics", top=1, research=True, model_spec=None,
                        as_of=AS_OF, board=_board())
    assert bought == []                                               # the morning's research was already saved
    board = _board_2()
    board["heat"] = [h for h in board["heat"] if h["theater_id"] != "thr_b"]
    res = daily_editions.produce(_ctx({"Alpha": _draft(), "Delta": _draft()}, SUMMARY_2), domain="geopolitics", top=5,
                                 research=True, model_spec=None, as_of=AS_OF, board=board)
    rows = {r["theater"]: r for r in res["theaters"]}
    assert rows["thr_a"]["research_reused"] is True
    assert bought == ["thr_d"]                                        # only the theater the morning lacked was commissioned
