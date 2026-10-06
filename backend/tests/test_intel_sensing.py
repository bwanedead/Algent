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


PUTIN = dict(role="President of Russia", affiliation="Russia")


def _seed_statements():
    """A Kremlin-heavy ledger shaped like the real one: generic Putin remarks about Russia and the West, one
    Valdai speech about NATO/EU/Ukraine, unrelated Kremlin news (CSTO exercises, a space shield, the election
    chief), a NATO reply, one French-budget statement, and one-off delegates from many countries."""
    d = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731
    rows = [_st("Vladimir Putin", d(3 + i % 11), f"Generic remark {i}.", about=("Russia", "West"), **PUTIN) for i in range(12)]
    rows += [
        _st("Vladimir Putin", d(1), "Says Europe's troops in Ukraine would be legitimate targets.", about=("NATO", "EU", "Ukraine", "West"),
            stance=-2, signal="threat", url=SPEECH, **PUTIN),
        _st("Vladimir Putin", d(1), "Accuses NATO circles of prolonging the war.", about=("NATO", "EU", "Ukraine"), stance=-1, **PUTIN),
        _st("Vladimir Putin", d(2), "Praises CSTO exercises.", about=("Russia", "CSTO", "Armenia"), **PUTIN),
        _st("Vladimir Putin", d(0), "Announces a space shield.", about=("Russia", "United States", "Space"), **PUTIN),
        _st("Vladimir Putin", d(40), "Says Russia is open to talks with NATO and the EU.", about=("NATO", "EU"), stance=1,
            signal="offer", **PUTIN),
        _st("Vladimir Putin", d(35), "Earlier CSTO remark.", about=("Russia", "CSTO"), **PUTIN),
        _st("Anna Pamfilova", d(2), "Reports on the election.", role="Chair of the Election Commission",
            affiliation="Russia", about=("Russia", "Elections")),
        _st("Mark Rutte", d(2), "NATO will defend every inch.", role="Secretary General", affiliation="NATO",
            about=("Russia", "Ukraine"), stance=-1),
        _st("Finance Ministry", d(2), "France cuts its budget deficit.", affiliation="France", about=("France", "Budget deficit")),
    ]
    rows += [_st(f"Delegate{i}", d(2), f"Remark from land {i}.", affiliation=f"Land{i}", about=(f"Land{i}", f"Place{i}"),
                 signal="other") for i in range(16)]
    assert sstore.append_statements(rows) == len(rows)
    return rows


RU_UA = Theater(id="thr_ru", name="Russia-Ukraine war and European security",
                why="NATO and the EU debate troops in Ukraine as Putin warns the West")
FRANCE = Theater(id="thr_fr", name="French budget austerity and political unrest",
                 why="Paris cuts its budget deficit; strikes follow", description="France protests")
AI_CHIPS = Theater(id="thr_ai", name="AI-driven RAM supply crunch", why="Memory makers race to supply AI data centers; shares and risk",
                   members=[])
ZORBIA = Theater(id="thr_z", name="Zorbia", why="Zorbia and Quillon dispute fishing quotas")


# ── selection ─────────────────────────────────────────────────────────────────────────────────
def test_instrument_tags_are_catalog_words_with_acronym_care() -> None:
    assert {"hormuz", "iran", "shipping"} <= set(sensing.instrument_tags("Iranian tankers avoid the Strait of Hormuz; shipping falls"))
    assert "us" not in sensing.instrument_tags("This will help us all")          # pronoun, not the country
    assert "us" in sensing.instrument_tags("New US sanctions")
    assert sensing.instrument_tags("Zorbia and Quillon dispute fishing quotas") == []


def test_rarity_cut_is_the_median_mention_and_a_flat_vocabulary_has_no_distinctive_items() -> None:
    docs = [{"common", "mid1"}, {"common", "mid1"}, {"common", "mid2"}, {"common", "mid2"}, {"common", "rare"}]
    r = sensing.rarity(docs)
    assert not r.distinctive("common") and r.distinctive("mid1") and r.distinctive("rare")
    assert r.idf["common"] == 0 and not r.distinctive("absent")
    flat = sensing.rarity([{"a"}, {"b"}])
    assert flat.distinctive("a") and flat.distinctive("b")                         # all equally rare: nothing is typical


def test_instruments_need_a_distinctive_series_subject_or_two_distinctive_tags() -> None:
    _seed_instruments()
    hormuz = Theater(id="thr_h", name="Strait of Hormuz closure", why="Iran halts tanker traffic; oil and energy markets react")
    ev = sensing.for_theater(hormuz, as_of=AS_OF)
    assert "chk_hormuz_transits" in ev.instruments and "UNUSUAL" in ev.instruments
    assert HORMUZ_URL in ev.instrument_urls
    assert YAHOO_URL not in ev.instrument_urls                                    # internal-source URLs are never offered as citable
    # generic macro words ("risk", US, "energy") do not drag the macro series into an AI theater
    macro = Theater(id="thr_m", name="AI boom and market risk", why="US equities, risk and energy demand from data centers",
                    members=[])
    assert sensing.for_theater(macro, as_of=AS_OF).instruments == ""
    assert sensing.for_theater(ZORBIA, as_of=AS_OF).instruments == ""


def test_a_tag_in_one_passing_headline_is_not_corroborated() -> None:
    from algent_backend.agent_system.agents.intel.contracts import Member
    one = Theater(id="thr_p", name="Border talks", why="A dispute", members=[
        Member(edition="e", n=1, title="Hormuz mentioned in passing", thesis="")])
    two = one.model_copy(update={"members": [*one.members, Member(edition="e", n=2, title="Hormuz again", thesis="")]})
    find = lambda t: set(sensing.instrument_tags(t))  # noqa: E731
    assert "hormuz" not in sensing.corroborated(find, one)
    assert "hormuz" in sensing.corroborated(find, two)


def test_real_failure_shapes_unrelated_theaters_get_no_kremlin_remarks_and_ru_ua_keeps_nato_eu() -> None:
    _seed_statements()
    ru = sensing.for_theater(RU_UA, as_of=AS_OF)
    assert SPEECH in ru.statements and "NATO circles" in ru.statements and "defend every inch" in ru.statements
    # "space shield" (a Russian strategic-defence claim aimed at the US and NATO) is part of the European security
    # dynamic since 10-05: two shared names (Russia, NATO) qualify a statement that is mainly about them.
    for unrelated in ("CSTO", "election", "land "):
        assert unrelated not in ru.statements
    # Routine remarks naming the theater's own actors ("Russia", "the West") may sit in the writer's pool; names
    # cannot tell routine from consequential. What must hold is the ORDER: none of them outranks the speech.
    order = [s.paraphrase for s in ru.shown]
    first_routine = next((i for i, p in enumerate(order) if p.startswith("Generic remark")), len(order))
    assert any(SPEECH == s.source_url for s in ru.shown[:first_routine])
    assert "STATEMENTS ON RECORD" in ru.statements and SPEECH in ru.statement_urls
    for theater in (FRANCE, AI_CHIPS, ZORBIA):
        ev = sensing.for_theater(theater, as_of=AS_OF)
        assert "Putin" not in ev.statements and "Pamfilova" not in ev.statements and ev.histories == [], theater.name
    assert "budget deficit" in sensing.for_theater(FRANCE, as_of=AS_OF).statements
    assert sensing.for_theater(AI_CHIPS, as_of=AS_OF).statements == ""
    assert sensing.for_theater(ZORBIA, as_of=AS_OF).render() == ""


def test_history_is_about_the_same_counterparts_not_the_speakers_other_news() -> None:
    _seed_statements()
    ev = sensing.for_theater(RU_UA, as_of=AS_OF)
    assert len(ev.histories) == 1 and "STATEMENT HISTORY: Vladimir Putin" in ev.histories[0]
    assert "open to talks with NATO and the EU" in ev.histories[0]                # tone toward the same counterparts
    assert "CSTO" not in ev.histories[0] and "Generic remark" not in ev.histories[0] and SPEECH not in ev.histories[0]


def test_surname_alias_only_for_a_speaker_whose_surname_is_theirs_alone() -> None:
    _seed_statements()
    voc = sensing.vocabulary(sstore.load_statements())
    assert sensing.statement_terms("Putin warns", voc) == {"vladimir putin"}
    assert sensing.statement_terms("putin the pronoun-less word", voc) == set()      # alias needs the capitalised surname
    # "States" is part of an entity ("United States"), "Minister"-like words are in titles: no alias for them
    assert not any(alias and phrase == ["states"] for _k, _s, phrase, alias in voc)


def test_previous_actors_widen_the_text() -> None:
    _seed_statements()
    t = Theater(id="thr_y", name="Border talks", why="A dispute")
    assert sensing.for_theater(t, as_of=AS_OF).statements == ""
    actors = sensing.prior_actors({"relations": [{"source": "NATO", "target": "EU"}]}, {"developments": [{"actors": ["Ukraine", "NATO"]}]})
    assert actors == ["NATO", "EU", "Ukraine"]
    assert "STATEMENTS ON RECORD" in sensing.for_theater(t, as_of=AS_OF, actors=actors).statements


def test_sensing_never_raises(monkeypatch) -> None:
    monkeypatch.setattr(sensing.store, "query", lambda **_k: (_ for _ in ()).throw(OSError("disk")))
    monkeypatch.setattr(sensing.store, "load_statements", lambda: (_ for _ in ()).throw(OSError("disk")))
    ev = sensing.for_theater(RU_UA, as_of=AS_OF)
    assert ev.error.startswith("OSError") and ev.render() == ""
    assert sensing.across_theaters(as_of=AS_OF).error.startswith("OSError")


# ── daily / brief / summary task text ─────────────────────────────────────────────────────────
def test_daily_section_task_carries_the_blocks_and_report_row_counts(tmp_path, monkeypatch) -> None:
    _store(tmp_path, monkeypatch)
    _seed_instruments()
    _seed_statements()
    tasks: list[str] = []
    board = _board()
    board["theaters"][0]["name"] = "Alpha"
    board["theaters"][0]["why"] = "NATO and the EU debate troops in Ukraine as Putin warns the West; Iran halts Hormuz tankers"
    board["theaters"][0]["description"] = "Strait of Hormuz"
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


def _seed_drift():
    """A debt-like series: rises most days with noisy steps; its latest reading is flagged but it only trends."""
    sid = "fisc_us_debt"
    vals, v = [], 30e12
    for i in range(300, 0, -1):
        v += (0.4e12 if i % 3 else -0.1e12) * (3 if i < 40 else 0.2)
        vals.append(_obs(sid, TODAY - timedelta(days=i), v))
    istore.append(sid, vals)


def test_trending_series_drop_out_of_the_cross_theater_list_but_a_collapse_stays() -> None:
    _seed_instruments()
    _seed_drift()
    day = TODAY
    assert sensing._trending("fisc_us_debt", day) and not sensing._trending("chk_hormuz_transits", day)
    ev = sensing.across_theaters(as_of=AS_OF)
    assert "chk_hormuz_transits" in ev.instruments and "fisc_us_debt" not in ev.instruments


def test_summary_gets_unusual_moves_and_top_statements_across_all_actors() -> None:
    _seed_instruments()
    _seed_statements()
    d = lambda n: (TODAY - timedelta(days=n)).isoformat()  # noqa: E731
    sstore.append_statements([_st("Vladimir Putin", d(0), f"Remark {i}", stance=-1, signal="warning", **PUTIN) for i in range(4)]
                             + [_st("Vladimir Putin", d(45), "ancient", stance=-2, **PUTIN)])
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
    sstore.append_statements([_st("Mark Rutte", d, "NATO is ready to deter Russia at Zaporizhzhia.", role="Secretary General",
                                  affiliation="NATO", about=("Russia", "Zaporizhzhia"))])
    t = RU_UA.model_copy(update={"why": RU_UA.why + "; Zaporizhzhia; Iran halts Hormuz tankers"})
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


def test_the_daily_is_dated_the_day_it_is_written_not_the_radar_board(tmp_path, monkeypatch, capsys) -> None:
    """A stale radar board (no edition today) once made 'today's' daily overwrite yesterday's record."""
    from datetime import date

    from algent_backend.agent_system.agents.intel import desk as desk_mod
    from algent_backend.cli.newsroom import intel as cli
    from algent_backend.cli.newsroom import pulse as pulse_cli
    from algent_backend.data_backup import sync
    from algent_backend.publishing import intel_page

    seen: list[str] = []
    monkeypatch.setattr(cli, "_ctx", lambda _id: object())
    monkeypatch.setattr(cli, "_heat", lambda *_a, **_k: 0)
    monkeypatch.setattr(cli, "_out", lambda as_of: tmp_path)
    monkeypatch.setattr(cli, "_prime", lambda *_a, **_k: [])
    monkeypatch.setattr(desk_mod, "latest_board", lambda: {"as_of": "2000-01-01", "theaters": [], "heat": []})
    monkeypatch.setattr(daily, "produce_daily", lambda *_a, **k: seen.append(k["as_of"]) or {
        "report": {"summary": {"headline": "h"}}, "path": "p", "theaters": [], "research_usd": 0.0})
    monkeypatch.setattr(intel_page, "publish_intel", lambda: {"published": True})
    monkeypatch.setattr(sync, "backup", lambda note="": {"ok": True})
    monkeypatch.setattr(pulse_cli, "promote_ready_quietly", lambda: [])

    class A:
        domain, top, research, fresh_research, days, no_refresh, date = "geopolitics", 5, False, False, 7, True, ""
    assert cli._daily(A()) == 0
    out = json.loads(capsys.readouterr().out)
    assert seen == [date.today().isoformat()] and out["date"] == seen[0]
    assert out["headlines_through"] == "2000-01-01"
    A.date = "2026-10-03"                      # an explicit rerun of a past day still works
    assert cli._daily(A()) == 0
    assert seen[-1] == "2026-10-03"


def test_a_joint_statement_naming_many_countries_is_not_on_the_record_of_each() -> None:
    """10-04: a White House science pact with seventeen countries led both the Russia–Ukraine and Hormuz
    records because it shared two names with each. A statement must be MAINLY about the theater's actors."""
    _seed_statements()
    d = (TODAY - timedelta(days=1)).isoformat()
    many = ("Ukraine", "NATO", "Japan", "India", "Brazil", "Kenya", "Chile", "Peru", "Ghana", "Norway", "Fiji",
            "Laos", "Oman", "Togo", "Chad", "Mali", "Niger")
    sstore.append_statements([_st("White House", d, "A golden age of science pact.", affiliation="United States",
                                  about=many, url="https://wh.example/science")])
    ev = sensing.for_theater(RU_UA, as_of=AS_OF)
    assert "golden age of science" not in ev.statements   # (the NATO/EU speech staying is covered above, without
    #                                                        17 one-off names skewing this tiny ledger's rarity cut)


def test_every_qualifying_red_line_reaches_the_writer_even_when_relevance_ranks_it_low() -> None:
    """10-05: fresh remarks outranked Putin's Kaliningrad red line on relevance and pushed it out of the pool."""
    _seed_statements()
    d = (TODAY - timedelta(days=1)).isoformat()
    sstore.append_statements([_st("Vladimir Putin", d, "Russia would use all its weapons if Kaliningrad were attacked.",
                                  about=("NATO", "Russia", "Kaliningrad"), signal="red_line", stance=-2,
                                  url="https://kremlin.example/redline", **PUTIN)])
    ev = sensing.for_theater(RU_UA, as_of=AS_OF, statement_limit=4)
    assert "https://kremlin.example/redline" in {x.source_url for x in ev.shown}    # shown to the writer, who picks
