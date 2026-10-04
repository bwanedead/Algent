"""Sensing: theater -> instrument tags / statement terms, the blocks in daily/brief/summary task text,
primary-evidence grounding, and best-effort refresh. Offline; fake models capture the task text."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from algent_backend.agent_system.agents.intel import brief as br
from algent_backend.agent_system.agents.intel import daily, desk, refresh, sensing
from algent_backend.agent_system.agents.intel.contracts import (
    Brief,
    ContextItem,
    DaySummary,
    Development,
    KeyFigure,
    SectionDraft,
    TimelineItem,
    Theater,
)
from algent_backend.agent_system.agents.statements import store as sstore
from algent_backend.agent_system.agents.statements.contracts import Statement, statement_id
from algent_backend.instruments import store as istore
from algent_backend.instruments.contracts import Observation
from tests.test_intel_daily import AS_OF, SUMMARY, _board, _ctx, _draft, _store

TODAY = date.fromisoformat(AS_OF)
HORMUZ_URL = "https://portwatch.imf.org/"
YAHOO_URL = "https://finance.yahoo.com/quote/BZ=F/"
SPEECH = "https://kremlin.example/speech"


@pytest.fixture(autouse=True)
def _stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_INSTRUMENTS_STORE", str(tmp_path / "istore"))
    monkeypatch.setenv("ALGENT_STATEMENTS_STORE", str(tmp_path / "sstore"))
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel"))


def _obs(sid, day, value):
    return Observation(series_id=sid, period=day.isoformat(), value=value, fetched_at="t", source_url="u")


def _seed_instruments():
    """Hormuz transits collapse to 2/day over the last week; Brent (internal source) is calm; wheat is calm."""
    hid = "chk_hormuz_transits"
    istore.append(hid, [_obs(hid, TODAY - timedelta(days=i), 100.0 + (i % 7) if i > 6 else 2.0) for i in range(300, 0, -1)])
    for sid in ("px_brent", "px_wheat"):
        istore.append(sid, [_obs(sid, TODAY - timedelta(days=i), 80.0 + (i % 5)) for i in range(300, 0, -1)])


def _st(speaker, day, text, *, role="", affiliation="", about=(), stance=0, signal="warning", url=None) -> Statement:
    url = url or f"https://src.example/{speaker.replace(' ', '-')}/{day}/{abs(hash(text)) % 999}"
    return Statement(id=statement_id(url, speaker, text), speaker=speaker, role=role, affiliation=affiliation, date=day,
                     paraphrase=text, about=list(about), signal=signal, stance=stance, significance="matters",
                     source_url=url, transcript_id="tr")


def _seed_statements():
    d = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731
    rows = [
        _st("Vladimir Putin", d(1), "Says Europe's troops in Ukraine would be legitimate targets.", role="President of Russia",
            affiliation="Russia", about=("EU", "Ukraine"), stance=-2, signal="threat", url=SPEECH),
        _st("Vladimir Putin", d(40), "Says Russia is open to talks with Europe.", role="President of Russia",
            affiliation="Russia", about=("EU",), stance=1, signal="offer"),
        _st("Mark Rutte", d(2), "NATO will defend every inch.", role="Secretary General", affiliation="NATO",
            about=("Russia",), stance=-1),
        _st("Quiet Official", d(2), "Welcomes the harvest report.", affiliation="Freedonia", about=("Freedonia",), signal="other"),
    ]
    assert sstore.append_statements(rows) == 4
    return rows


def _theater(name="Russia and Europe", why="Putin and NATO trade threats over troops in Ukraine and the Strait of Hormuz"):
    return Theater(id="thr_x", name=name, why=why)


# ── selection ─────────────────────────────────────────────────────────────────────────────────
def test_instrument_tags_are_catalog_words_with_acronym_care() -> None:
    assert {"hormuz", "iran", "shipping"} <= set(sensing.instrument_tags("Iranian tankers avoid the Strait of Hormuz; shipping falls"))
    assert "us" not in sensing.instrument_tags("This will help us all")          # pronoun, not the country
    assert "us" in sensing.instrument_tags("New US sanctions")
    assert sensing.instrument_tags("Zorbia and Quillon dispute fishing quotas") == []


def test_theater_gets_matching_readings_ranked_by_specific_tags_and_none_when_unrelated() -> None:
    _seed_instruments()
    ev = sensing.for_theater(_theater(), as_of=AS_OF)
    assert "chk_hormuz_transits" in ev.instruments and ev.n_instruments >= 1
    assert "UNUSUAL" in ev.instruments                                            # the collapse is flagged
    assert "px_wheat" in ev.instruments                                           # Ukraine/Russia tags reach wheat too
    lone = sensing.for_theater(_theater("Strait", "Traffic in the Strait of Hormuz"), as_of=AS_OF)
    assert "px_wheat" not in lone.instruments and "chk_hormuz_transits" in lone.instruments.splitlines()[1]   # unusual first
    assert HORMUZ_URL in ev.instrument_urls
    assert YAHOO_URL not in ev.instrument_urls                                    # internal-source URLs are never offered as citable
    none = sensing.for_theater(_theater("Zorbia", "Zorbia and Quillon dispute fishing quotas"), as_of=AS_OF)
    assert none.instruments == "" and none.statements == "" and none.render() == "" and not none.primary_urls


def test_theater_gets_statements_by_ledger_entities_with_speaker_history() -> None:
    _seed_statements()
    ev = sensing.for_theater(_theater(), as_of=AS_OF)
    assert {"Russia", "NATO", "Ukraine", "putin"} <= set(ev.terms)
    assert "STATEMENTS ON RECORD" in ev.statements and SPEECH in ev.statements and "defend every inch" in ev.statements
    assert "harvest" not in ev.statements                                         # unrelated actor
    # Putin's older, softer statement is history (not repeated in the recall block); the speech is not duplicated there
    assert len(ev.histories) == 1 and "STATEMENT HISTORY: Vladimir Putin" in ev.histories[0]
    assert "open to talks" in ev.histories[0] and SPEECH not in ev.histories[0]
    assert SPEECH in ev.statement_urls
    none = sensing.for_theater(_theater("Zorbia", "Zorbia and Quillon dispute fishing quotas"), as_of=AS_OF)
    assert none.statements == "" and none.histories == []


def test_previous_actors_widen_the_text() -> None:
    _seed_statements()
    t = Theater(id="thr_y", name="Border talks", why="A dispute")
    assert sensing.for_theater(t, as_of=AS_OF).statements == ""
    actors = sensing.prior_actors({"relations": [{"source": "Russia", "target": "EU"}]},
                                  {"developments": [{"actors": ["NATO", "Russia"]}]})
    assert actors == ["Russia", "EU", "NATO"]
    assert "STATEMENTS ON RECORD" in sensing.for_theater(t, as_of=AS_OF, actors=actors).statements


def test_sensing_never_raises(monkeypatch) -> None:
    monkeypatch.setattr(sensing.store, "query", lambda **_k: (_ for _ in ()).throw(OSError("disk")))
    ev = sensing.for_theater(_theater(), as_of=AS_OF)
    assert ev.error.startswith("OSError") and ev.render() == ""
    assert sensing.across_theaters(as_of=AS_OF).error.startswith("OSError")


# ── daily / brief / summary task text ─────────────────────────────────────────────────────────
def test_daily_section_task_carries_the_blocks_and_report_row_counts(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    _seed_instruments()
    _seed_statements()
    tasks: list[str] = []
    board = _board()
    board["theaters"][0]["why"] = "Putin and NATO trade threats; Hormuz transits collapse"
    ctx = _ctx({"Alpha": _draft(), "Bravo": _draft(pulses=[])}, SUMMARY, tasks)
    res = daily.produce_daily(ctx, domain="geopolitics", top=5, research=False, model_spec=None, as_of=AS_OF,
                              board=board)
    alpha = next(t for t in tasks if "THEATER: Alpha" in t)
    assert "INSTRUMENTS" in alpha and "chk_hormuz_transits" in alpha and "STATEMENTS ON RECORD" in alpha and SPEECH in alpha
    bravo = next(t for t in tasks if "THEATER: Bravo" in t)
    assert "INSTRUMENTS" not in bravo and "STATEMENTS ON RECORD" not in bravo
    rows = {r["theater"]: r for r in res["theaters"]}
    assert rows["thr_a"]["sensing"]["instruments"] >= 1 and rows["thr_a"]["sensing"]["statements"] >= 1
    assert rows["thr_b"]["sensing"] == {"instruments": 0, "statements": 0}


def test_summary_gets_unusual_moves_and_top_statements_across_all_actors() -> None:
    _seed_instruments()
    _seed_statements()
    d = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731
    sstore.append_statements([_st("Vladimir Putin", d(0), f"Remark {i}", stance=-1, signal="warning") for i in range(4)]
                             + [_st("Vladimir Putin", d(45), "ancient", stance=-2)])
    ev = sensing.across_theaters(as_of=AS_OF)
    assert "chk_hormuz_transits" in ev.instruments and "px_wheat" not in ev.instruments          # only flagged ones
    assert SPEECH in ev.statements
    assert ev.statements.count("Vladimir Putin") <= sensing.PER_SPEAKER_CAP
    assert "ancient" not in ev.statements and "open to talks" not in ev.statements                # last ~3 days only
    tasks: list[str] = []
    sections = [{"name": "Alpha", "temperature": {"trend": "steady", "coverage": "steady coverage"}, "bottom_line": "b",
                 "escalation": {"direction": "steady", "pace": "flat"}, "developments": []}]
    daily.write_summary(_ctx({}, SUMMARY, tasks), None, sections, as_of=AS_OF, domain="geopolitics", model_spec=None,
                        sensing=ev)
    assert "ACROSS ALL THEATERS AND ACTORS" in tasks[0] and "chk_hormuz_transits" in tasks[0] and SPEECH in tasks[0]
    daily.write_summary(_ctx({}, SUMMARY, tasks), None, sections, as_of=AS_OF, domain="geopolitics", model_spec=None)
    assert "ACROSS ALL" not in tasks[1]


def test_brief_task_carries_blocks_with_the_longer_window_and_primary_urls_ground_the_timeline(tmp_path) -> None:
    _seed_instruments()
    _seed_statements()
    d = (TODAY - timedelta(days=20)).isoformat()
    sstore.append_statements([_st("Mark Rutte", d, "NATO is ready to deter Russia.", role="Secretary General",
                                  affiliation="NATO", about=("Russia",))])
    t = _theater()
    ev = sensing.for_theater(t, as_of=AS_OF, statement_days=desk.BRIEF_WINDOW_DAYS, statement_limit=desk.BRIEF_STATEMENTS)
    assert "ready to deter" in ev.statements and "last 30 days" in ev.statements
    short = sensing.for_theater(t, as_of=AS_OF)                                  # the daily's fortnight misses it
    assert "ready to deter" not in short.statements
    tasks: list[str] = []
    result = Brief(title="t", bottom_line="b", timeline=[
        TimelineItem(date="2026-09-28", what="Putin threatens", verification="researched", source=SPEECH),
        TimelineItem(date="2026-09-28", what="invented", verification="researched", source="https://invented.example")])

    class _M:
        def with_structured_output(self, _s):
            return self

        def invoke(self, messages, **_k):
            tasks.append(messages[1].content)
            return result
    ctx = type("X", (), {"model_resolver": type("R", (), {"resolve": lambda _s, _sp: type("C", (), {"client": _M()})()})()})()
    out = br.write_brief(ctx, None, t, {}, profiles=[], pulse_table={}, model_spec=None, sensing=ev)
    assert "STATEMENTS ON RECORD" in tasks[0] and "chk_hormuz_transits" in tasks[0] and "STATEMENT HISTORY" in tasks[0]
    assert [i.verification for i in out.timeline] == ["researched", "reported"]


# ── grounding ─────────────────────────────────────────────────────────────────────────────────
def _normalise(draft, **kw):
    return daily.normalise_section(draft, pulse_table={}, has_previous=False, researched=False, research_urls=set(),
                                   reported_urls=set(), **kw)


def test_primary_urls_are_citable_and_grounded_but_unknown_urls_are_not() -> None:
    draft = _draft(
        developments=[Development(headline="speech", sources=[SPEECH], verification="researched"),
                      Development(headline="number", sources=[HORMUZ_URL + "/"], verification="researched"),
                      Development(headline="invented", sources=["https://invented.example"], verification="researched")],
        context=[ContextItem(what="old speech", source=SPEECH, verification="researched"),
                 ContextItem(what="invented", source="https://invented.example", verification="researched")],
        key_figures=[KeyFigure(label="Hormuz transits", value=2, unit="ships/day", baseline=102,
                               baseline_label="a year earlier", as_of="2026-09-28", source=HORMUZ_URL),
                     KeyFigure(label="From a transcript", value=5, as_of="2026-09-28", source=SPEECH),
                     KeyFigure(label="Unknown", value=5, as_of="2026-09-28", source="https://invented.example")])
    out = _normalise(draft, instrument_urls={HORMUZ_URL}, statement_urls={SPEECH})
    assert [(d.verification, d.sources) for d in out.developments] == [
        ("researched", [SPEECH]), ("researched", [HORMUZ_URL + "/"]), ("reported", [])]
    assert [(c.verification, c.source) for c in out.context] == [("researched", SPEECH), ("reported", "")]
    assert [f.label for f in out.key_figures] == ["Hormuz transits"]              # a statement is not a source for a number
    bare = _normalise(_draft(developments=[Development(headline="x", sources=[SPEECH], verification="researched")]))
    assert bare.developments[0].verification == "reported" and bare.developments[0].sources == []   # absent evidence: unchanged


def test_doctrine_is_one_integrated_evidence_paragraph() -> None:
    for role in (daily.DAILY_ROLE, br.ANALYST_ROLE):
        low = role.lower()
        assert "two kinds of evidence" not in low
        assert "said, not that" in low and "instruments" in low and "statements on record" in low
        assert "own history" in low or "earlier statements" in low and "as-of" in low
    assert "instruments" in daily.SUMMARY_ROLE.lower() and "said" in daily.SUMMARY_ROLE.lower()
    assert "instruments" in daily.DAILY_ROLE.split("`key_figures`")[1].lower()


# ── refresh ───────────────────────────────────────────────────────────────────────────────────
def test_refresh_isolates_layer_failures_and_never_raises() -> None:
    def boom():
        raise RuntimeError("provider down")
    out = refresh.refresh(None, None, instruments=boom, statements=lambda c, m: {"transcripts_collected": 2})
    assert out["instruments"]["error"].startswith("RuntimeError") and out["statements"] == {"transcripts_collected": 2}
    out = refresh.refresh(None, None, instruments=lambda: {"ok": 3}, statements=lambda c, m: boom())
    assert out["instruments"] == {"ok": 3} and "provider down" in out["statements"]["error"]


def test_a_failed_refresh_does_not_fail_the_daily_and_no_refresh_skips(tmp_path, monkeypatch, capsys) -> None:
    from algent_backend.agent_system.agents.intel import desk as desk_mod
    from algent_backend.cli.newsroom import intel as cli
    from algent_backend.data_backup import sync
    from algent_backend.publishing import intel_page

    monkeypatch.setattr(refresh, "refresh", lambda *_a, **_k: refresh_report)
    refresh_report = {"instruments": {"error": "RuntimeError: down"}, "statements": {"error": "RuntimeError: down"}}
    monkeypatch.setattr(cli, "_ctx", lambda _id: object())
    monkeypatch.setattr(cli, "_heat", lambda *_a, **_k: 0)
    monkeypatch.setattr(cli, "_out", lambda as_of: tmp_path)
    monkeypatch.setattr(cli, "_prime", lambda *_a, **_k: [])
    monkeypatch.setattr(desk_mod, "latest_board", lambda: {"as_of": AS_OF, "theaters": [], "heat": []})
    monkeypatch.setattr(daily, "produce_daily", lambda *_a, **_k: {
        "report": {"summary": {"headline": "h"}}, "path": "p", "theaters": [], "research_usd": 0.0})
    monkeypatch.setattr(intel_page, "publish_intel", lambda: {"published": True})
    monkeypatch.setattr(sync, "backup", lambda note="": {"ok": True})
    from algent_backend.cli.newsroom import pulse as pulse_cli
    monkeypatch.setattr(pulse_cli, "promote_ready_quietly", lambda: [])

    class A:
        domain, top, research, fresh_research, days = "geopolitics", 5, False, False, 7
        no_refresh = False
    assert cli._daily(A()) == 0
    assert json.loads(capsys.readouterr().out)["sensing_refresh"]["instruments"]["error"] == "RuntimeError: down"
    A.no_refresh = True
    assert cli._daily(A()) == 0
    assert json.loads(capsys.readouterr().out)["sensing_refresh"] == {"skipped": "--no-refresh"}
