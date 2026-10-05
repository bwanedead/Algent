"""The desk's focus follows the world: a broad base, measured novelty, a lifecycle, and a focus with a ceiling."""

from __future__ import annotations

import json
from datetime import date, timedelta

from algent_backend.agent_system.agents.intel import base, daily, focus, heat, novelty, sensing
from algent_backend.agent_system.agents.intel.contracts import Member, Theater

from test_intel_daily import AS_OF, SUMMARY, _ctx, _draft, _store

TODAY = date(2026, 10, 4)


def _day(back: int) -> str:
    return (TODAY - timedelta(days=back)).isoformat()


def _head(kind: str, day: str, i: int, title: str, group: str = "g") -> dict:
    return {"id": f"{kind}-{day}#{i}", "day": day, "kind": kind, "edition": f"{day}-{kind}", "n": i, "title": title,
            "thesis": "", "sources": [f"https://x/{kind}/{i}"], "group": group}


# ── the broad base ────────────────────────────────────────────────────────────────────────────
def test_dedupe_is_by_content_words_within_a_class() -> None:
    heads = [_head("library", _day(0), 1, "Iran seizes a tanker in Hormuz"),
             _head("library", _day(0), 2, "Iran seizes tanker in Hormuz!"),
             _head("library", _day(0), 3, "Rail strike in Germany")]
    assert [h["n"] for h in base.dedupe(heads)] == [1, 3]


def test_water_filling_gives_small_classes_whole_and_thins_the_big_one() -> None:
    assert base.quotas({"radar": 40, "wikipedia": 50, "library": 5000}, 300) == {"radar": 40, "wikipedia": 50, "library": 210}
    assert base.quotas({"a": 500, "b": 500}, 300) == {"a": 150, "b": 150}
    assert base.quotas({"a": 3}, 300) == {"a": 3}


def test_the_cut_is_spread_over_days_and_groups() -> None:
    heads = [_head("library", _day(d), i, f"t{d}{i}", group=g) for d in (0, 1) for i, g in enumerate("aaaabb")]
    shown = base.spread(heads, 4)
    assert len(shown) == 4
    assert {h["day"] for h in shown} == {_day(0), _day(1)}                    # both days represented
    assert {h["group"] for h in shown} == {"a", "b"}                          # and both groups


EDITIONS = [{"slug": f"{_day(1)}-0800", "leads": [{"n": i, "title": f"radar {i}"} for i in range(1, 11)]}]


def _loaders(wiki: list[dict], lib: list[dict]):
    return {base.WIKIPEDIA: lambda days, today: wiki, base.LIBRARY: lambda days, today: lib}


def test_assemble_tags_classes_and_counts_the_shown_per_day() -> None:
    wiki = [_head("wikipedia", _day(0), i, f"wiki event {i}") for i in range(1, 5)]
    lib = [_head("library", _day(0), i, f"doc {i}", group=f"s{i % 2}") for i in range(1, 9)]
    b = base.assemble(EDITIONS, days=7, today=TODAY, loaders=_loaders(wiki, lib), budget=12)
    assert b.pool == {"radar": 10, "wikipedia": 4, "library": 8}
    # budget 12: equal shares of 4; wikipedia has exactly 4, radar and library are thinned to 4
    assert {c: v["shown"] for c, v in b.summary().items()} == {"radar": 4, "wikipedia": 4, "library": 4}
    assert {h["kind"] for h in b.heads.values()} == {"radar", "wikipedia", "library"}
    assert b.sizes["radar"] == {_day(1): sum(1 for h in b.heads.values() if h["kind"] == "radar")}


def test_a_class_that_fails_to_load_is_absent_not_fatal() -> None:
    b = base.assemble(EDITIONS, days=7, today=TODAY, loaders={base.WIKIPEDIA: lambda d, t: []})
    assert set(b.pool) == {"radar"} and len(b.heads) == 10


# ── heat: share per class, mean across classes ────────────────────────────────────────────────
def _members(kind: str, day: str, n: int) -> list[Member]:
    return [Member(edition=f"{day}-{kind}", n=i, kind=kind, title="x") for i in range(n)]


def test_heat_is_the_mean_of_per_class_shares_and_a_missing_class_is_absent() -> None:
    t = Theater(id="thr_t", name="T", members=_members("radar", _day(0), 4) + _members("wikipedia", _day(0), 1))
    sizes = {"radar": {_day(0): 40}, "wikipedia": {_day(0): 10}, "library": {_day(0): 1000}}
    h = heat.measure(t, [], days=7, today=TODAY, sizes=sizes)
    # radar 4/40 = .10, wikipedia 1/10 = .10, library 0/1000 = 0  ->  mean .0667 (library did not dominate)
    assert h.recent_share == round((0.10 + 0.10 + 0.0) / 3, 4)
    assert h.by_class["radar"].recent == 4 and h.by_class["radar"].recent_n == 40
    # a class with no headlines in the window (radar skipped) is left out of the mean, not counted as zero
    gap = heat.measure(t, [], days=7, today=TODAY, sizes={"wikipedia": {_day(0): 10}, "radar": {}})
    assert gap.recent_share == 0.1


def test_one_class_reduces_to_the_old_test_and_classes_corroborate() -> None:
    assert heat._judge([(10, 100, 20, 100)]) == "cooling" and heat._judge([(20, 100, 10, 100)]) == "heating"
    assert heat._judge([(3, 10, 2, 10)]) == "steady"
    # two classes that each lean the same way beat the noise that one alone does not
    one = (4, 20, 2, 20)
    assert heat._judge([one]) == "steady" and heat._judge([one, one, one, one]) == "heating"
    assert heat._judge([]) == "steady"


# ── novelty ───────────────────────────────────────────────────────────────────────────────────
def test_novelty_counts_new_headlines_statements_and_newly_flagged_series(monkeypatch) -> None:
    t = Theater(id="thr_t", name="T", members=[*_members("radar", _day(5), 2), *_members("radar", _day(1), 1),
                                              *_members("library", _day(0), 2), *_members("wikipedia", _day(2), 1)])
    ev = sensing.Evidence(statement_dates=[_day(6), _day(3), _day(0)], tags=["oil"],
                          instrument_rows=[{"series_id": "brent"}, {"series_id": "debt"}])
    flags = {TODAY: {"brent": _day(0), "debt": _day(0)}, date.fromisoformat(_day(4)): {"debt": _day(4)}}
    monkeypatch.setattr(novelty, "_flagged", lambda tags, day: flags.get(day, {}))
    n = novelty.measure(t, since=_day(4), as_of=TODAY, ev=ev)
    assert n["headlines"] == {"radar": 1, "wikipedia": 1, "library": 2}      # day-5 items were already covered
    assert n["statements"] == 2 and n["instruments"] == 1                      # debt was already off its range
    assert n["total"] == 7 and n["newest"] == _day(0) and n["since"] == _day(4)
    none = novelty.measure(t, since=_day(0), as_of=TODAY, ev=None)
    assert none["total"] == 0 and none["newest"] == ""


# ── lifecycle ─────────────────────────────────────────────────────────────────────────────────
def test_the_drop_and_the_return() -> None:
    def state(last_novel: str, *, covered=True, first_seen="2026-08-01") -> str:
        return focus.classify(last_novel=last_novel, first_seen=first_seen, covered=covered, as_of=TODAY, days=7)

    assert focus.FOCUS_DROP_DAYS == 7
    assert state(_day(0)) == "active" and state(_day(6)) == "active"
    assert state(_day(7)) == "quiet" and state("") == "quiet"                  # a week of nothing: it falls off
    assert state(_day(0)) == "active"                                          # novelty returns: active again
    assert state(_day(1), covered=False, first_seen=_day(2)) == "new"
    assert state(_day(1), covered=True, first_seen=_day(2)) == "active"        # once written up it is no longer new


def test_annotate_persists_last_novel_and_revives_a_quiet_theater(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path))
    monkeypatch.setattr(sensing, "for_theater", lambda *a, **k: sensing.Evidence())
    reg = {"thr_a": {"name": "A", "first_seen": _day(30), "last_seen": _day(12), "domain": "geopolitics"},
           "thr_b": {"name": "B", "first_seen": _day(30), "last_seen": _day(2), "last_novel": _day(2)}}
    focus.annotate([], [], reg, as_of=TODAY, days=7, covered_before=TODAY.isoformat())
    assert reg["thr_a"]["last_novel"] == _day(12) and reg["thr_a"]["state"] == "quiet"   # legacy seeded from last_seen
    assert reg["thr_b"]["state"] == "active"
    # A comes back: re-clustered with a headline today
    t = Theater(id="thr_a", name="A", members=_members("radar", _day(0), 2))
    h = heat.measure(t, [], days=7, today=TODAY, sizes={"radar": {_day(0): 10}})
    focus.annotate([t], [h], reg, as_of=TODAY, days=7, covered_before=TODAY.isoformat())
    assert h.state == "active" and reg["thr_a"]["last_novel"] == _day(0) and reg["thr_a"]["state"] == "active"
    assert h.novelty["headlines"]["radar"] == 2


# ── the focus ─────────────────────────────────────────────────────────────────────────────────
def _row(tid: str, heat_: float, total: int, state: str = "active", since: str = "2026-10-01") -> dict:
    return {"theater_id": tid, "name": tid.upper(), "heat": heat_, "trend": "steady", "state": state,
            "last_novel": "2026-10-03", "novelty": {"total": total, "since": since, "headlines": {}}}


def _board(rows: list[dict], lifecycle: list[dict] | None = None) -> dict:
    return {"as_of": "2026-10-04", "theaters": [{"id": r["theater_id"], "name": r["name"], "domain": "geopolitics",
                                                 "members": []} for r in rows],
            "heat": rows, "lifecycle": lifecycle or []}


def test_focus_ranks_by_heat_times_novelty_under_a_ceiling_and_lists_the_rest() -> None:
    rows = [_row("a", 10, 1), _row("b", 4, 9), _row("c", 8, 2), _row("d", 30, 0), _row("e", 5, 3, state="quiet")]
    p = focus.plan(_board(rows), 2, ["geopolitics"])
    assert p.focus == ["b", "c"]                                               # 36, 16 beat a's 10
    by_id = {w["theater_id"]: w for w in p.watch}
    assert by_id["a"]["reason"] == "over_budget" and by_id["d"]["reason"] == "nothing_new"
    assert by_id["d"]["note"] == "No new developments since 2026-10-01."
    assert [q["theater_id"] for q in p.quiet] == ["e"]
    # a busy world fills the ceiling, a quiet one does not
    assert len(focus.plan(_board(rows), 10, None).focus) == 3
    assert focus.plan(_board([_row("d", 30, 0)]), 5, None).focus == []


def test_offboard_theaters_join_watch_and_quiet_and_never_covered_quiet_ones_are_not_listed() -> None:
    life = [{"theater_id": "x", "name": "X", "domain": "geopolitics", "state": "active", "last_novel": "2026-10-02",
             "last_section": "2026-10-01"},
            {"theater_id": "y", "name": "Y", "domain": "geopolitics", "state": "quiet", "last_novel": "2026-09-20",
             "last_section": "2026-09-19", "countries": ["Iran"]},
            {"theater_id": "z", "name": "Z", "domain": "geopolitics", "state": "quiet", "last_novel": "2026-09-01",
             "last_section": ""}]
    p = focus.plan(_board([_row("a", 1, 1)], life), 5, ["geopolitics"])
    assert [w["theater_id"] for w in p.watch] == ["x"] and p.watch[0]["note"].endswith("2026-10-01.")
    assert [q["theater_id"] for q in p.quiet] == ["y"] and p.quiet[0]["countries"] == ["Iran"]


def test_a_board_without_lifecycle_keeps_the_old_top_by_heat() -> None:
    old = {"theaters": [{"id": "a", "domain": "geopolitics"}, {"id": "b", "domain": "geopolitics"}],
           "heat": [{"theater_id": "a", "heat": 1.0}, {"theater_id": "b", "heat": 2.0}]}
    p = focus.plan(old, 1, ["geopolitics"])
    assert p.focus == ["b"] and p.watch == [] and p.quiet == []


# ── end to end: board -> registry -> daily record ─────────────────────────────────────────────
class _Plan:
    def __init__(self, plan):
        self.plan = plan

    def with_structured_output(self, _s):
        return self

    def invoke(self, *_a, **_k):
        return self.plan


def test_run_builds_a_board_with_classes_novelty_state_and_persists_the_registry(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path))
    monkeypatch.setattr(sensing, "for_theater", lambda *a, **k: sensing.Evidence())
    wiki = [_head("wikipedia", _day(0), i, f"wiki {i}") for i in range(1, 4)]
    lib = [_head("library", _day(1), i, f"doc {i}") for i in range(1, 4)]
    eds = [{"slug": f"{_day(2)}-0800", "leads": [{"n": i, "title": f"radar {i}"} for i in range(1, 6)]}]
    plan = heat.TheaterPlan(theaters=[heat.ProposedTheater(name="Alpha", headline_ids=[
        f"{_day(2)}-0800#1", wiki[0]["id"], lib[0]["id"]])])
    ctx = type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": _Plan(plan)})()})()})()
    board = heat.run(ctx, None, eds, model_spec=None, days=7, loaders=_loaders(wiki, lib), today=TODAY)
    assert board["as_of"] == TODAY.isoformat() and board["headlines"] == 11
    assert board["base"]["wikipedia"] == {"pool": 3, "shown": 3}
    row = board["heat"][0]
    assert {m["kind"] for m in board["theaters"][0]["members"]} == {"radar", "wikipedia", "library"}
    assert set(row["by_class"]) == {"radar", "wikipedia", "library"}
    assert row["state"] == "new" and row["novelty"]["total"] == 3 and row["last_novel"] == _day(0)
    saved = json.loads((tmp_path / "theaters.json").read_text(encoding="utf-8"))
    assert saved["thr_alpha"]["state"] == "new" and saved["thr_alpha"]["last_novel"] == _day(0)
    # a dry run touches nothing
    (tmp_path / "theaters.json").unlink()
    heat.run(ctx, None, eds, model_spec=None, days=7, loaders=_loaders(wiki, lib), today=TODAY, write=False)
    assert not (tmp_path / "theaters.json").exists()


def test_the_daily_writes_focus_sections_and_records_watch_and_quiet(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    rows = [_row("thr_a", 9, 4, since="2026-09-28"), _row("thr_b", 5, 0, since="2026-09-28")]
    board = _board(rows, [{"theater_id": "thr_q", "name": "Quiet one", "domain": "geopolitics", "state": "quiet",
                           "last_novel": "2026-09-10", "last_section": "2026-09-09"}])
    board["as_of"] = AS_OF
    board["theaters"][0]["members"] = [{"edition": "2026-09-29-0800", "n": 1, "title": "t", "thesis": "t",
                                        "sources": []}]
    tasks: list[str] = []
    ctx = _ctx({"THR_A": _draft()}, SUMMARY, tasks)
    res = daily.produce_daily(ctx, domain="geopolitics", top=5, model_spec=None, as_of=AS_OF, board=board)
    rec = res["report"]
    assert [t["theater_id"] for t in rec["theaters"]] == ["thr_a"]            # b had nothing new: not written
    assert [w["theater_id"] for w in rec["watch"]] == ["thr_b"] and rec["watch"][0]["reason"] == "nothing_new"
    assert [q["theater_id"] for q in rec["quiet"]] == ["thr_q"]


def test_the_writer_is_told_what_is_new_or_that_nothing_is() -> None:
    prev = {"_date": "2026-09-28"}
    assert daily.new_since_line({}, prev) == "" and daily.new_since_line({"novelty": {"total": 1}}, None) == ""
    nothing = daily.new_since_line({"novelty": {"total": 0, "since": "2026-09-28"}}, prev)
    assert "NEW SINCE 2026-09-28: nothing" in nothing
    some = daily.new_since_line({"novelty": {"total": 3, "since": "2026-09-28", "newest": "2026-09-30",
                                             "headlines": {"radar": 2, "library": 0, "wikipedia": 1},
                                             "statements": 1, "instruments": 0}}, prev)
    assert "2 radar, 1 wikipedia" in some and "1 statements" in some
    assert "short and says so" in daily.DAILY_ROLE
