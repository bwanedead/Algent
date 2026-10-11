"""The world sweep ("Around the world") and the Spotlight: parsing and guards, exclusion of the focus, the
nomination respecting recent coverage, and the daily's integration (fake model, no network)."""

from __future__ import annotations

import json

import pytest

from algent_backend.agent_system.agents.intel import daily, sweep

from test_intel_daily import AS_OF, SRC_A, SRC_B, SUMMARY, _board, _draft, _Model, _store

SRC_C, SRC_D = "https://news.example/sahel", "https://news.example/arctic"


def _item(**kw) -> sweep.SweepItemDraft:
    base = dict(region="Africa", text="Gold mine seized in the Sahel; supply to refiners at risk.",
                countries=["ml", "BF", "xx", "Mali", "ml"], sources=[SRC_B])
    return sweep.SweepItemDraft(**{**base, **kw})


def _mat() -> sweep.Material:
    return sweep.Material(text="m", urls={SRC_B, SRC_C, SRC_D})


class _SweepModel(_Model):
    """The daily's fake, plus a reply for the sweep schema (and a tape of its tasks)."""

    def __init__(self, drafts, summary, tasks, sweep_reply):
        super().__init__(drafts, summary, tasks)
        self.sweep_reply = sweep_reply

    def invoke(self, messages, **_k):
        if self.schema is sweep.SweepDraft:
            self.tasks.append(messages[1].content)
            if isinstance(self.sweep_reply, Exception):
                raise self.sweep_reply
            return self.sweep_reply
        return super().invoke(messages, **_k)


def _ctx(drafts, reply, tasks):
    model = _SweepModel(drafts, SUMMARY, tasks, reply)
    return type("X", (), {"model_resolver": type("R", (), {
        "resolve": lambda _s, _spec: type("C", (), {"client": model})()})()})()


@pytest.fixture(autouse=True)
def _offline_library(monkeypatch):
    """Sweep material from the source library is a local read; tests hand it in instead."""
    monkeypatch.setattr(sweep, "library_material", lambda _as_of: [])
    monkeypatch.setattr(sweep.sensing_mod, "across_theaters", lambda **_k: sweep.sensing_mod.Evidence())


def _board_with_world() -> dict:
    board = _board()
    board["theaters"][1]["members"].append({"edition": "2026-09-29-0900", "n": 2, "title": "Sahel gold",
                                            "thesis": "t", "sources": [SRC_C]})
    board["theaters"][1]["members"].append({"edition": "2026-09-01-0900", "n": 3, "title": "Old news",
                                            "thesis": "t", "sources": [SRC_D]})      # outside the ~48h window
    return board


def _run(tmp_path, monkeypatch, reply, *, research=False, tasks=None, drafts=None, board=None):
    _store(tmp_path, monkeypatch)
    monkeypatch.setattr(daily.br, "obtain_research", lambda *a, **k: (None, False))
    tasks = [] if tasks is None else tasks
    ctx = _ctx(drafts or {"Alpha": _draft(), "Sahel gold": _draft(pulses=[])}, reply, tasks)
    return daily.produce_daily(ctx, domain="geopolitics", top=1, research=research, model_spec=None, as_of=AS_OF,
                               board=board or _board_with_world()), tasks


# ── parsing and guards ────────────────────────────────────────────────────────────────────────
def test_items_survive_only_with_a_source_from_the_material_and_real_codes() -> None:
    draft = sweep.SweepDraft(items=[
        _item(),
        _item(text="made up", sources=["https://invented.example/x"]),                 # not in the material
        _item(text="no source at all", sources=[]),
        _item(text="", sources=[SRC_C]),
        _item(region="Arctic", text="Basing deal in Greenland.", countries=["gl", "DK"], sources=[SRC_C + "/", SRC_D]),
    ])
    kept = [r for _it, r in sweep.clean(draft, _mat(), covered_urls=set(), known_iso={"ML", "BF", "GL", "DK"})]
    assert [r["text"] for r in kept] == ["Gold mine seized in the Sahel; supply to refiners at risk.",
                                         "Basing deal in Greenland."]
    assert kept[0]["countries"] == ["ML", "BF"]            # upper-cased, deduped, "xx" unknown, "Mali" not a code
    assert kept[1]["sources"] == [SRC_C + "/", SRC_D]      # trailing-slash variants match; the writer's form is kept


def test_an_item_resting_only_on_what_the_focus_sections_cite_is_dropped() -> None:
    draft = sweep.SweepDraft(items=[_item(sources=[SRC_B]), _item(text="two sources", sources=[SRC_B, SRC_C])])
    kept = [r for _it, r in sweep.clean(draft, _mat(), covered_urls={SRC_B})]
    assert [r["sources"] for r in kept] == [[SRC_C]]       # the second keeps only its fresh source


def test_gather_leaves_out_the_focus_and_the_old_and_adds_unclaimed_library_titles() -> None:
    lib = [{"id": "l1", "day": AS_OF, "kind": "library", "title": "Treaty on a river", "thesis": "mfa",
            "sources": ["https://lib.example/river"], "group": "mfa"},
           {"id": "l2", "day": AS_OF, "kind": "library", "title": "Already clustered", "thesis": "mfa",
            "sources": [SRC_B], "group": "mfa"}]
    mat = sweep.gather(_board_with_world(), domain="geopolitics", focus_ids={"thr_a"}, as_of=AS_OF,
                       library=lambda _a: lib, evidence=sweep.sensing_mod.Evidence())
    assert SRC_A not in mat.urls and "Alpha headline" not in mat.text           # focus theater: covered elsewhere
    assert SRC_D not in mat.urls                                                # older than the window
    assert {SRC_B, SRC_C, "https://lib.example/river"} <= mat.urls
    assert mat.text.count(SRC_B) == 1                                           # the clustered title is not repeated
    assert set(mat.eligible) == {"thr_b"}


# ── the nomination ────────────────────────────────────────────────────────────────────────────
def test_a_spotlight_on_a_board_theater_uses_it_and_an_unknown_one_is_built_from_its_headlines() -> None:
    mat = sweep.Material(urls={SRC_B, SRC_C}, heads={SRC_C: {"title": "Sahel gold", "thesis": "t", "day": AS_OF,
                                                             "kind": "radar"}},
                         eligible={"thr_b": daily.Theater(id="thr_b", name="Bravo")})
    pairs = sweep.clean(sweep.SweepDraft(items=[
        _item(spotlight=True, title="Bravo dynamic", theater_id="thr_b"),
        _item(text="Second", sources=[SRC_C], spotlight=True, title="Sahel gold seizures")]), mat, covered_urls=set())
    _it, theater = sweep._nominee(pairs, mat, set(), "geopolitics")
    assert theater.id == "thr_b"
    _it, adhoc = sweep._nominee(pairs[1:], mat, set(), "geopolitics")
    assert adhoc.id == "thr_spot_sahel_gold_seizures" and adhoc.members[0].sources == [SRC_C]
    # nothing headline-shaped behind it (a statement URL only) -> nothing to build a theater from
    no_head = sweep.clean(sweep.SweepDraft(items=[_item(spotlight=True, title="X", sources=[SRC_B])]), mat,
                          covered_urls=set())
    assert sweep._nominee(no_head, mat, set(), "geopolitics") == (None, None)


def test_the_nomination_respects_what_the_daily_covered_in_the_last_span(tmp_path, monkeypatch) -> None:
    folder = tmp_path / "intel" / "daily" / "geopolitics"
    folder.mkdir(parents=True)

    def write(date, rec):
        (folder / f"{date}.json").write_text(json.dumps({"date": date, **rec}), encoding="utf-8")
    write("2026-09-26", {"theaters": [{"theater_id": "thr_b", "name": "Bravo", "bottom_line": "x"}]})
    write("2026-09-27", {"theaters": [], "sweep": {"spotlight": {"theater_id": "thr_spot_sahel_gold_seizures"},
                                                    "regions": [{"region": "Africa", "items": [{"text": "old flag"}]}]}})
    write("2026-09-01", {"theaters": [{"theater_id": "thr_old", "name": "Old", "bottom_line": "x"}]})   # outside
    text, ids = sweep.recent_coverage(folder, before=AS_OF)
    assert ids == {"thr_b", "thr_spot_sahel_gold_seizures"} and "old flag" in text and "Old" not in text

    mat = sweep.Material(urls={SRC_B, SRC_C}, heads={SRC_C: {"title": "h", "thesis": "", "day": AS_OF, "kind": "radar"}},
                         eligible={"thr_b": daily.Theater(id="thr_b", name="Bravo")})
    pairs = sweep.clean(sweep.SweepDraft(items=[
        _item(spotlight=True, title="Bravo again", theater_id="thr_b"),
        _item(text="Sahel again", sources=[SRC_C], spotlight=True, title="Sahel gold seizures")]), mat,
        covered_urls=set())
    assert sweep._nominee(pairs, mat, ids, "geopolitics") == (None, None)       # both covered within the span
    assert sweep._nominee(pairs, mat, set(), "geopolitics")[1].id == "thr_b"    # sanity: free to nominate otherwise


# ── the daily ─────────────────────────────────────────────────────────────────────────────────
def test_the_daily_carries_the_sweep_grouped_by_region_and_excludes_the_focus(tmp_path, monkeypatch) -> None:
    reply = sweep.SweepDraft(items=[
        _item(sources=[SRC_C]), _item(text="second Africa", countries=["NG"], sources=[SRC_B]),
        _item(region="Arctic", text="invented", sources=["https://invented.example/z"]),
        _item(region="Europe", text="Rests on the focus", sources=[SRC_A])])
    res, tasks = _run(tmp_path, monkeypatch, reply)
    task = next(t for t in tasks if "MATERIAL:" in t)
    assert SRC_C in task and "Alpha headline" not in task and "Old news" not in task
    rec = json.loads((tmp_path / "intel" / "daily" / "geopolitics" / f"{AS_OF}.json").read_text(encoding="utf-8"))
    assert rec == res["report"] and [t["theater_id"] for t in rec["theaters"]] == ["thr_a"]
    assert rec["sweep"]["regions"] == [{"region": "Africa", "items": [
        {"text": "Gold mine seized in the Sahel; supply to refiners at risk.", "countries": ["ML", "BF"], "sources": [SRC_C]},
        {"text": "second Africa", "countries": ["NG"], "sources": [SRC_B]}]}]
    assert rec["sweep"]["spotlight"] is None and rec["schema"] == "ohmega.daily/1"


def test_a_spotlight_gets_one_extra_researched_section_only_with_research(tmp_path, monkeypatch) -> None:
    reply = sweep.SweepDraft(items=[_item(sources=[SRC_C], spotlight=True, title="Sahel gold")])
    plain, _ = _run(tmp_path / "a", monkeypatch, reply, research=False)
    spot = plain["report"]["sweep"]["spotlight"]
    assert spot["name"] == "Sahel gold" and spot["adhoc"] and spot["section"] is False
    assert [t["theater_id"] for t in plain["report"]["theaters"]] == ["thr_a"]       # nothing paid without --research

    res, tasks = _run(tmp_path / "b", monkeypatch, reply, research=True)
    ids = [t["theater_id"] for t in res["report"]["theaters"]]
    assert ids == ["thr_a", "thr_spot_sahel_gold"] and res["report"]["sweep"]["spotlight"]["section"] is True
    assert "spotlight" not in res["report"]["theaters"][0] and res["report"]["theaters"][1]["spotlight"] is True
    assert any("THEATER: Sahel gold" in t for t in tasks)
    assert next(r for r in res["theaters"] if r["theater"] == "thr_spot_sahel_gold")["spotlight"] is True
    assert res["report"]["sweep"]["regions"][0]["items"][0]["spotlight"] is True


def test_a_spotlight_never_adds_more_than_the_flag_allows(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_SPOTLIGHT_SECTIONS", "0")
    reply = sweep.SweepDraft(items=[_item(sources=[SRC_C], spotlight=True, title="Sahel gold")])
    res, _ = _run(tmp_path, monkeypatch, reply, research=True)
    assert [t["theater_id"] for t in res["report"]["theaters"]] == ["thr_a"]


def test_a_failed_sweep_costs_only_the_sweep(tmp_path, monkeypatch) -> None:
    res, _ = _run(tmp_path, monkeypatch, RuntimeError("504 gateway_timeout"))
    assert "sweep" not in res["report"] and [t["theater_id"] for t in res["report"]["theaters"]] == ["thr_a"]
    assert "sweep failed" in next(r for r in res["theaters"] if r["theater"] == "(sweep)")["error"]
    assert res["report"]["summary"]["headline"] == "Alpha heats up"


def test_the_flag_switches_the_sweep_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_SWEEP", "0")
    res, tasks = _run(tmp_path, monkeypatch, sweep.SweepDraft(items=[_item(sources=[SRC_C])]))
    assert "sweep" not in res["report"] and not any("MATERIAL:" in t for t in tasks)
