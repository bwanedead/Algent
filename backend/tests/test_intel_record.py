"""The visible record: on_record rows (build, persistence, back-compat), the cited-statement regression, the
bounded record export and tone series, and the Pulse display-label cache. Offline; fake models only."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from algent_backend.agent_system.agents.intel import daily, desk, dossier, on_record, pulse_labels, sensing
from algent_backend.agent_system.agents.intel.contracts import Brief, Development
from algent_backend.agent_system.agents.pulse import PulseStore
from algent_backend.agent_system.agents.pulse.contracts import Pulse, PulseDefinition, Situation
from algent_backend.agent_system.agents.statements import store as sstore
from algent_backend.publishing import intel_page
from tests.test_intel_daily import AS_OF, SUMMARY, _board, _ctx, _draft, _store
from tests.test_intel_sensing import RU_UA, SPEECH, _seed_statements, _st

TODAY = date.fromisoformat(AS_OF)


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path / "sstore"))
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))


def _day(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


# ── on_record rows ────────────────────────────────────────────────────────────────────────────
def test_entry_carries_the_statement_flag_and_link() -> None:
    s = _st("Vladimir Putin", _day(1), "Warns the West.", role="President of Russia", affiliation="Russia",
            about=("Ukraine", "NATO"), stance=-2, signal="threat", url=SPEECH)
    row = on_record.entry(s)
    assert row["speaker"] == "Vladimir Putin" and row["iso2"] == "RU" and row["url"] == SPEECH
    assert row["about_iso2"] == ["UA"] and row["paraphrase"] == "Warns the West." and row["quote"] == ""
    assert on_record.entry(_st("Mark Rutte", _day(1), "x", affiliation="NATO"))["iso2"] == ""   # not a country


def test_build_keeps_sensings_order_and_dedupes() -> None:
    a, b = _st("A", _day(1), "one", affiliation="France"), _st("B", _day(2), "two", affiliation="Germany")
    assert [r["speaker"] for r in on_record.build([b, a, b])] == ["B", "A"]


def test_merge_is_newest_first_deduped_and_ignores_records_without_the_field() -> None:
    old = on_record.entry(_st("A", _day(5), "old"))
    new = on_record.entry(_st("B", _day(1), "new"))
    assert [r["speaker"] for r in on_record.merge([[old], None, [new, old], []])] == ["B", "A"]
    assert len(on_record.merge([[old], [new]], limit=1)) == 1


# ── the diagnosed failure ─────────────────────────────────────────────────────────────────────
def test_a_development_that_cites_a_transcript_but_left_statements_empty_gets_them_attached() -> None:
    """The 10-04 daily: developments cited statement transcripts (gov.uk, state.gov) and every `statements` list
    was empty, so the site showed no quotes. The writer pointed at the transcript; the desk writes down what
    it pointed at."""
    rec = on_record.build([_st("Vladimir Putin", _day(1), "Says troops are targets.", role="President of Russia",
                               affiliation="Russia", url=SPEECH)])
    draft = _draft(developments=[Development(headline="Speech", sources=[SPEECH], verification="researched"),
                                 Development(headline="Other", sources=["https://wire.example/a"])])
    out = daily.normalise_section(draft, pulse_table={}, has_previous=False, researched=False, research_urls=set(),
                                  reported_urls={"https://wire.example/a"}, statement_urls={SPEECH}, record=rec)
    first, second = out.developments
    assert [(s.who, s.said, s.source, s.when, s.quote) for s in first.statements] == [
        ("Vladimir Putin", "Says troops are targets.", SPEECH, _day(1), False)]
    assert second.statements == []
    again = daily.normalise_section(out, pulse_table={}, has_previous=False, researched=False, research_urls=set(),
                                    reported_urls=set(), statement_urls={SPEECH}, record=rec)
    assert len(again.developments[0].statements) == 1          # what the writer already carried is not doubled


def test_attached_quotes_are_verbatim_and_trimmed_like_any_quote() -> None:
    words = " ".join(f"w{i}" for i in range(40))
    s = _st("X", _day(1), "paraphrase", url=SPEECH).model_copy(update={"quote": words})
    out = daily.normalise_section(
        _draft(developments=[Development(headline="d", sources=[SPEECH])]), pulse_table={}, has_previous=False,
        researched=False, research_urls=set(), reported_urls=set(), statement_urls={SPEECH},
        record=on_record.build([s]))
    st = out.developments[0].statements[0]
    assert st.quote and st.said.startswith("w0 w1") and st.said.endswith("…") and len(st.said.split()) == daily.MAX_QUOTE_WORDS + 1


def test_the_doctrine_asks_for_statements_on_developments_that_rest_on_them() -> None:
    assert "carries it here" in daily.DAILY_ROLE and "transcript link" in daily.DAILY_ROLE
    assert "cites the transcript link as its `source`" in __import__(
        "algent_backend.agent_system.agents.intel.brief", fromlist=["x"]).ANALYST_ROLE


# ── persistence ───────────────────────────────────────────────────────────────────────────────
def _alpha_board():
    board = _board()
    board["theaters"][0]["why"] = "NATO and the EU debate troops in Ukraine as Putin warns the West"
    return board


def test_daily_sections_persist_on_record_in_sensings_order_whatever_the_writer_did(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    _seed_statements()
    ctx = _ctx({"Alpha": _draft(developments=[Development(headline="Speech", sources=[SPEECH], verification="researched")]),
                "Bravo": _draft(pulses=[])}, SUMMARY)
    res = daily.produce_daily(ctx, domain="geopolitics", top=5, research=False, model_spec=None, as_of=AS_OF,
                              board=_alpha_board())
    alpha, bravo = res["report"]["theaters"]
    assert alpha["on_record"] and bravo["on_record"] == []
    expected = sensing.for_theater(
        daily.Theater.model_validate(_alpha_board()["theaters"][0]), as_of=AS_OF).shown
    assert [r["id"] for r in alpha["on_record"]] == [s.id for s in expected]
    row = next(r for r in alpha["on_record"] if r["url"] == SPEECH)
    assert row["iso2"] == "RU" and row["speaker"] == "Vladimir Putin" and row["signal"] == "threat"
    assert alpha["developments"][0]["statements"][0]["who"] == "Vladimir Putin"       # the cited transcript, attached
    stored = json.loads((tmp_path / "intel" / "daily" / "geopolitics" / f"{AS_OF}.json").read_text(encoding="utf-8"))
    assert stored["theaters"][0]["on_record"] == alpha["on_record"]


def test_a_brief_persists_on_record_and_a_brief_without_it_is_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))
    brief = Brief(title="t", bottom_line="b")
    plain = desk.persist_brief(brief, as_of=AS_OF, theater=RU_UA, heat={}, researched=False)
    assert "on_record" not in plain
    rows = on_record.build([_st("A", _day(1), "x", affiliation="France")])
    with_rec = desk.persist_brief(brief, as_of=AS_OF, theater=RU_UA, heat={}, researched=False, focus="f",
                                  on_record_rows=rows)
    assert with_rec["on_record"] == rows


def test_dossier_unions_dailies_and_briefs_deduped_and_old_records_still_build() -> None:
    a, b = on_record.entry(_st("A", _day(3), "a")), on_record.entry(_st("B", _day(1), "b"))
    section = lambda d, rec: {"theater_id": "thr_x", "name": "X", "developments": [], **({"on_record": rec} if rec is not None else {})}  # noqa: E731
    reports = [{"date": _day(3), "built_at": "t1", "domain": "g", "theaters": [section(_day(3), [a])]},
               {"date": _day(2), "built_at": "t2", "domain": "g", "theaters": [section(_day(2), None)]}]   # an old record
    brief = {"slug": "s", "as_of": _day(1), "built_at": "t3", "theater_id": "thr_x", "on_record": [b, a]}
    out = dossier.build_all(dossier.Inputs(reports=reports, briefs=[brief]))["theaters"]["thr_x"]
    assert [r["speaker"] for r in out["on_record"]] == ["B", "A"]
    assert dossier.build_all(dossier.Inputs(reports=reports[1:]))["theaters"]["thr_x"]["on_record"] == []


# ── the export ────────────────────────────────────────────────────────────────────────────────
def test_export_is_bounded_by_window_and_count(monkeypatch) -> None:
    sstore.append_statements([_st(f"S{i}", _day(i), f"text {i}", affiliation="France") for i in (0, 1, 2, 59, 61, 100)])
    out = on_record.export(today=TODAY)
    assert out["schema"] == "ohmega.record/1" and out["window_days"] == 60
    assert [s["speaker"] for s in out["statements"]] == ["S0", "S1", "S2", "S59"]        # 61 and 100 days: out of the window
    assert out["count"] == 4 and out["newest"] == _day(0)
    monkeypatch.setattr(on_record, "MAX_STATEMENTS", 2)
    assert [s["speaker"] for s in on_record.export(today=TODAY)["statements"]] == ["S0", "S1"]


def test_publish_writes_the_record_beside_the_other_desk_files(tmp_path, monkeypatch) -> None:
    sstore.append_statements([_st("A", _day(1), "x", affiliation="France")])
    store = PulseStore(tmp_path / "pulses")
    snapshot = intel_page.build_snapshot(store, tmp_path / "intel")
    site = tmp_path / "site"
    intel_page.write_intel(site, snapshot, tmp_path / "intel", None)
    for where in (site / "content" / "intel" / "record.json", site / "public" / "data" / "record.json"):
        rec = json.loads(where.read_text(encoding="utf-8"))
        assert rec["schema"] == "ohmega.record/1" and rec["count"] == 1


# ── tone ──────────────────────────────────────────────────────────────────────────────────────
def test_tone_series_needs_enough_statements_over_enough_days_and_averages_each_day() -> None:
    rows = [_st("Putin", _day(d), f"t{d}{k}", affiliation="Russia", about=("NATO", "Russia"), stance=s)
            for d, k, s in ((5, 0, -2), (5, 1, -1), (3, 0, -2), (1, 0, -1))]
    rows += [_st("Putin", _day(1), "few", affiliation="Russia", about=("Mars",), stance=2),        # one statement: no series
             _st("Putin", _day(2), "same day only a", affiliation="Russia", about=("Peru",), stance=1),
             _st("Putin", _day(2), "same day only b", affiliation="Russia", about=("Peru",), stance=1),
             _st("Putin", _day(2), "same day only c", affiliation="Russia", about=("Peru",), stance=1),
             _st("Putin", _day(2), "same day only d", affiliation="Russia", about=("Peru",), stance=1)]
    tone = on_record.tone_series(rows)
    assert [(t["affiliation"], t["about"], t["n"]) for t in tone] == [("Russia", "NATO", 4)]    # not Russia -> Russia
    assert tone[0]["iso2"] == "RU" and tone[0]["about_iso2"] == "" and tone[0]["mean"] == -1.5
    assert tone[0]["points"] == [{"date": _day(5), "stance": -1.5, "n": 2}, {"date": _day(3), "stance": -2.0, "n": 1},
                                 {"date": _day(1), "stance": -1.0, "n": 1}]


# ── Pulse display labels ──────────────────────────────────────────────────────────────────────
class _Labeler:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def with_structured_output(self, schema):
        assert schema is pulse_labels.LabelDraft
        return self

    def invoke(self, messages, **_k):
        self.calls.append(messages[1].content)
        return self.replies.pop(0)


def _ctx_for(model):
    return type("X", (), {"model_resolver": type("R", (), {"resolve": lambda _s, _sp: type("C", (), {"client": model})()})()})()


def _pulse_store(tmp_path) -> PulseStore:
    store = PulseStore(tmp_path / "pulses")
    store.save_situation(Situation(id="sit_uc", title="US-China relations", summary="s", status="active"))
    store.save_situation(Situation(id="sit_old", title="Old", status="dormant"))
    store.create_pulse(Pulse(id="pls_dd", situation_id="sit_uc", name="Relationship deadlock",
                             definitions=[PulseDefinition(question="How locked is the relationship?")]))
    store.create_pulse(Pulse(id="pls_old", situation_id="sit_old", name="Old pulse",
                             definitions=[PulseDefinition(question="q")]))
    return store


def test_label_fallback_is_deterministic_and_never_needs_a_model(tmp_path) -> None:
    labels = pulse_labels.load(tmp_path)
    assert labels == {}
    assert pulse_labels.display(labels, "pls_dd", "US-China relations", "Relationship deadlock") == {
        "title": "US-China relations · Relationship deadlock", "actors_iso2": []}
    snap = intel_page.build_snapshot(_pulse_store(tmp_path), tmp_path / "intel")
    pulse = snap["situations"][0]["pulses"][0]
    assert pulse["title"] == "US-China relations · Relationship deadlock" and pulse["actors_iso2"] == []


def test_labels_are_built_once_cached_and_remade_only_when_the_definition_version_changes(tmp_path) -> None:
    store = _pulse_store(tmp_path)
    model = _Labeler([pulse_labels.LabelDraft(title="  US–China · Diplomatic deadlock ·", actors_iso2=["us", "CN", "UK", "cn", "x1", "FR", "DE"])])
    out = pulse_labels.build_missing(_ctx_for(model), store, model_spec=None, root=tmp_path)
    assert out["built"] == ["pls_dd"] and out["failed"] == [] and len(model.calls) == 1      # the dormant situation's Pulse: skipped
    label = pulse_labels.load(tmp_path)["pls_dd"]
    assert label["title"] == "US–China · Diplomatic deadlock" and label["actors_iso2"] == ["US", "CN", "GB"]
    assert label["label_version"] == 1
    again = pulse_labels.build_missing(_ctx_for(_Labeler([])), store, model_spec=None, root=tmp_path)    # no reply queued: a call would raise
    assert again["built"] == [] and again["reused"] == 1
    store.add_definition("pls_dd", PulseDefinition(question="New ruler"))
    remade = _Labeler([pulse_labels.LabelDraft(title="US–China · Deadlock", actors_iso2=["US", "CN"])])
    out = pulse_labels.build_missing(_ctx_for(remade), store, model_spec=None, root=tmp_path)
    assert out["built"] == ["pls_dd"] and pulse_labels.load(tmp_path)["pls_dd"]["label_version"] == 2
    forced = _Labeler([pulse_labels.LabelDraft(title="US–China · Deadlock v3", actors_iso2=[])])
    assert pulse_labels.build_missing(_ctx_for(forced), store, model_spec=None, root=tmp_path, refresh=True)["built"] == ["pls_dd"]


def test_a_failed_or_empty_label_is_reported_not_cached_and_publish_uses_cached_labels(tmp_path, monkeypatch) -> None:
    store = _pulse_store(tmp_path)
    out = pulse_labels.build_missing(_ctx_for(_Labeler([pulse_labels.LabelDraft(title="   ")])), store, model_spec=None, root=tmp_path)
    assert out["built"] == [] and out["failed"][0]["error"] == "no usable title" and pulse_labels.load(tmp_path) == {}
    boom = type("B", (), {"with_structured_output": lambda s, _x: s, "invoke": lambda s, *_a, **_k: (_ for _ in ()).throw(RuntimeError("down"))})()
    assert pulse_labels.build_missing(_ctx_for(boom), store, model_spec=None, root=tmp_path)["failed"][0]["error"].startswith("RuntimeError")
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))
    pulse_labels.build_missing(_ctx_for(_Labeler([pulse_labels.LabelDraft(title="US–China · Deadlock", actors_iso2=["US", "CN"])])),
                               store, model_spec=None, root=tmp_path / "intel")
    pulse = intel_page.build_snapshot(store, tmp_path / "intel")["situations"][0]["pulses"][0]
    assert pulse["title"] == "US–China · Deadlock" and pulse["actors_iso2"] == ["US", "CN"] and pulse["name"] == "Relationship deadlock"
    feed = intel_page.build_pulse_feed(store)["pulses"][0]
    assert feed["title"] == "US–China · Deadlock" and feed["actors_iso2"] == ["US", "CN"]


def test_lead_with_puts_the_writers_key_statements_first_and_keeps_every_row() -> None:
    from algent_backend.agent_system.agents.intel import on_record

    rows = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
    assert [r["id"] for r in on_record.lead_with(rows, ["S3", "[S1]", "S3", "S9", "x"])] == ["c", "a", "b", "d"]
    assert on_record.lead_with(rows, []) == rows
