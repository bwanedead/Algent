"""Calendar: schedule parsers on small saved fragments, store sync/withdraw, corpus extraction, the COMING UP block, publish."""

from __future__ import annotations

from datetime import date

import pytest

from algent_backend.lookahead import collect as collect_mod
from algent_backend.lookahead import desk, extract, store
from algent_backend.lookahead import publish as pub
from algent_backend.lookahead.contracts import make, short
from algent_backend.lookahead.sources import central_banks as cb
from algent_backend.lookahead.sources import elections, un_opec

TODAY = date(2026, 10, 16)

FED = """<div class="panel-heading"><h4><a id="1">2026 FOMC Meetings</a></h4></div>
<div class="fomc-meeting__month col"><strong>October</strong></div><div class="fomc-meeting__date col">27-28</div>
<div class="fomc-meeting__month col"><strong>December</strong></div><div class="fomc-meeting__date col">8-9*</div>
<div class="panel-heading"><h4><a id="2">2025 FOMC Meetings</a></h4></div>
<div class="fomc-meeting__month col"><strong>December</strong></div><div class="fomc-meeting__date col">9-10*</div>"""

ECB = """<div>28/10/2026</div><div>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 1)</div>
<div>29/10/2026</div><div>Governing Council of the ECB: monetary policy meeting in Frankfurt (Day 2), followed by press conference</div>
<div>25/11/2026</div><div>Governing Council of the ECB: non-monetary policy meeting (in Frankfurt)</div>"""

BOE = """<h2>2026 confirmed dates</h2><table><tbody>
<tr><td>Thursday 17 September</td><td>x</td></tr><tr><td>Thursday 5 November</td><td>x</td></tr>
<tr><td>Thursday&nbsp;17 December</td><td>x</td></tr></tbody></table><h2>2027 confirmed dates</h2><table><tbody>
<tr><td>Thursday 4 February</td><td>x</td></tr></tbody></table>"""

WIKI = """==October==
* 3 October: [[Elections in Latvia|Latvia]], [[2026 Latvian parliamentary election|Parliament]]<ref name="x">cite</ref>
* 9–10 October: [[Elections in the Czech Republic|Czech Republic]], [[2026 Czech Senate election|Senate (1st round)]]
* 25 October:
** [[Elections in Bulgaria|Bulgaria]], [[2026 Bulgarian presidential election|President]]<ref>{{Cite web |url=http://x}}</ref>
** [[Elections in Serbia|Serbia]], [[2026 Serbian parliamentary election|Parliament]]
* 27 October: [[Elections in Israel|Israel]], [[2026 Israeli legislative election|Knesset]]
* November: [[Elections in Nowhere|Nowhere]], undated
==November==
* 3 November: [[Elections in the United States|United States]], [[2026 United States House of Representatives elections|House of Representatives]] and [[x|Senate]]
"""

_UNSC_JSON = (
    '{"title":"<div class=\\"calendar-event-datetime\\">15:00<\\/div>10244th meeting - Syria","id":"a","eid":"1",'
    '"url":"\\/securitycouncil\\/en\\/events\\/10244th-meeting-syria","des":"Off","editable":false,"start":"2026-10-21T15:00:00"},'
    '{"title":"<div class=\\"calendar-event-datetime\\">11:00<\\/div>Military Staff Committee formal meeting","id":"b","eid":"2",'
    '"url":"\\/x","des":"Off","editable":false,"start":"2026-10-22T11:00:00"}')
# the page embeds the JSON inside drupalSettings with quotes and angle brackets written as backslash-u escapes
UNSC = _UNSC_JSON.replace('"', chr(92) + "u0022").replace("<", chr(92) + "u003C").replace(">", chr(92) + "u003E")


def test_central_banks():
    fed = cb.parse_fed(FED)
    assert [(i.date, i.title) for i in fed] == [("2026-10-28", "Fed rate decision (FOMC)"), ("2026-12-09", "Fed rate decision with projections"),
                                                  ("2025-12-10", "Fed rate decision with projections")]
    assert [i.date for i in cb.parse_ecb(ECB)] == ["2026-10-29"]
    boe = cb.parse_boe(BOE)
    assert [i.date for i in boe] == ["2026-09-17", "2026-11-05", "2026-12-17", "2027-02-04"] and boe[0].countries == ["GB"]


def test_elections_parse():
    items = elections.parse(WIKI, 2026)
    by = {i.title: i for i in items}
    assert by["Latvia: Parliament"].date == "2026-10-03" and by["Latvia: Parliament"].countries == ["LV"]
    assert by["Czech Republic: Senate (1st round)"].end_date == "2026-10-10"
    assert "Bulgaria: President" in by and "Serbia: Parliament" in by and by["Serbia: Parliament"].date == "2026-10-25"
    assert by["United States: House of Representatives and Senate"].date == "2026-11-03"
    assert not any("Nowhere" in t for t in by)               # a month with no day is not a date


def test_unsc_parse_keeps_numbered_meetings_only():
    items = un_opec.parse_unsc(UNSC)
    assert [(i.date, i.title) for i in items] == [("2026-10-21", "UN Security Council: Syria")]
    assert items[0].countries == ["SY"] and items[0].source_url.startswith("https://main.un.org/securitycouncil/en/events/")


def test_opec_next_meeting():
    text = "The 68th Meeting of the JMMC was held. The next meeting of the JMMC (69th) is scheduled for 29 November 2026."
    got = un_opec.parse_opec_release(text, "https://www.opec.org/pr-detail/x", TODAY)
    assert [(i.date, i.title, i.confidence) for i in got] == [("2026-11-29", "OPEC+ JMMC meeting", "medium")]


def test_short_title_and_ids():
    assert short("one two three four five six seven eight nine ten eleven twelve,") == "one two three four five six seven eight nine ten"
    a, b = make("deadline", "corpus", "2026-11-01", "Waiver expires", "u"), make("deadline", "corpus", "2026-11-01", "waiver  EXPIRES", "u")
    assert a.id == b.id


@pytest.fixture
def cal(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_CALENDAR_STORE", str(tmp_path / "cal"))
    return tmp_path


def test_sync_new_changed_withdrawn(cal):
    a, b = make("central_bank", "fed", "2026-10-28", "Fed rate decision (FOMC)", "u"), make("central_bank", "fed", "2026-12-09", "Fed rate decision (FOMC)", "u")
    assert store.sync("fed", [a, b], TODAY) == {"new": 2, "changed": 0, "withdrawn": 0, "unchanged": 0}
    again = store.sync("fed", [a, b], TODAY)
    assert again["unchanged"] == 2 and again["new"] == 0
    res = store.sync("fed", [a], TODAY)                     # the December date is no longer listed
    assert res["withdrawn"] == 1
    cur = store.current()
    assert cur[b.id].active is False and cur[a.id].active is True
    assert [i.id for i in store.upcoming(TODAY, 90)] == [a.id]
    assert len(store.revisions()) == 3                      # history kept


def test_refresh_isolates_and_never_withdraws_on_empty(cal):
    item = make("election", "elections", "2026-10-25", "Serbia: Parliament", "u", countries=["RS"])
    store.sync("elections", [item], TODAY)

    def boom(_t):
        raise RuntimeError("blocked")

    rep = collect_mod.refresh(["elections", "unsc"], today=TODAY, fetchers={"elections": lambda _t: [], "unsc": boom})
    assert [r["status"] for r in rep["sources"]] == ["error", "error"]
    assert store.current()[item.id].active                  # an empty answer did not cancel the election
    assert "blocked" in store.load_status()["unsc"]["last_error"]


def test_extract_from_sentences():
    text = "The waiver for Russian oil payments expires on 3 November 2026. Parliament will vote on the budget on 12 December. It happened on 2 October."
    items = extract.items_from_text(text, today=TODAY, url="https://x/y", theater="thr_a", via="daily:2026-10-16:thr_a")
    kinds = {(i.kind, i.date) for i in items}
    assert ("deadline", "2026-11-03") in kinds and ("vote", "2026-12-12") in kinds and len(items) == 2   # the past date is ignored
    assert all(i.confidence == "low" and i.provenance == "ohmega_derived" and i.theaters == ["thr_a"] for i in items)
    assert all(len(i.title.split()) <= 10 for i in items)
    assert extract.items_from_text("Talks resume next Tuesday, the deadline is tomorrow.", today=TODAY, url="u") == []


def test_attach_accumulates_theaters(cal):
    sec = {"theater_id": "thr_a", "developments": [{"headline": "Deal nears", "detail": "The truce expires on 20 November 2026.", "actors": ["Israel"],
                                                     "where": "Gaza", "sources": ["https://news/x"]}], "watch_next": ["Summit scheduled for 5 December 2026 in Riyadh."]}
    res = extract.attach([sec], as_of="2026-10-16")
    assert res["found"] == 2 and res["new"] == 2
    sec2 = dict(sec, theater_id="thr_b")
    extract.attach([sec2], as_of="2026-10-17")
    dl = next(i for i in store.current().values() if i.kind == "deadline")
    assert dl.theaters == ["thr_a", "thr_b"] and dl.countries == ["IL"] and dl.source_url == "https://news/x"


def test_desk_block_matches_theater_or_country(cal):
    fed = make("central_bank", "fed", "2026-10-28", "Fed rate decision (FOMC)", "https://fed/x", countries=["US"])
    ours = make("deadline", "corpus", "2026-10-30", "Truce expires", "https://news/x", theaters=["thr_a"], confidence="low", provenance="ohmega_derived")
    far = make("election", "elections", "2027-03-01", "Far: Parliament", "u", countries=["US"])
    store.sync("fed", [fed], TODAY)
    store.sync("corpus", [ours], TODAY, withdraw=False)
    store.sync("elections", [far], TODAY)
    text, urls, n = desk.for_theater({"US"}, "thr_other", TODAY)
    assert n == 1 and "Fed rate decision" in text and urls == {"https://fed/x"}
    text, urls, n = desk.for_theater(set(), "thr_a", TODAY)
    assert n == 1 and "EARLIER REPORT" in text and urls == set()      # our own report is never cited as a source
    assert desk.for_theater(set(), "thr_zzz", TODAY) == ("", set(), 0)


def test_publish_rows(cal):
    store.sync("fed", [make("central_bank", "fed", "2026-10-28", "Fed rate decision (FOMC)", "u", countries=["US"])], TODAY)
    sent: list = []

    class Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def executemany(self, sql, rows): sent.extend(rows)

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def cursor(self): return Cur()
        def commit(self): pass

    assert pub.publish(today=TODAY, connect=lambda: Conn())["items"] == 1
    assert sent[0][1] == "2026-10-28" and sent[0][2] is None and sent[0][5] == ["US"] and sent[0][-1] is True


def test_sensing_carries_the_coming_up_block(cal):
    from algent_backend.agent_system.agents.intel import sensing
    from algent_backend.agent_system.agents.intel.contracts import Theater

    store.sync("fed", [make("central_bank", "fed", "2026-10-28", "Fed rate decision (FOMC)", "https://fed/x", countries=["US"])], TODAY)
    store.sync("boe", [make("central_bank", "boe", "2026-11-05", "Bank of England rate decision", "https://boe/x", countries=["GB"])], TODAY)
    th = Theater(id="thr_us", name="United States tariffs and the dollar", why="Washington's trade moves")
    text, urls, n = sensing._coming_block(th, (), TODAY)
    assert n == 1 and "Fed rate decision" in text and urls == {"https://fed/x"}      # the BoE date is a country this theater does not stand behind
    ev = sensing.Evidence(coming=text, coming_urls=urls)
    assert "COMING UP" in ev.render() and "https://fed/x" in ev.primary_urls
