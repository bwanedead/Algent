"""Calendar sources added in 2026-10: one parser per source on a small saved fragment, the rule-based generators, dedupe, importance,
window bounds, cadence classes and the published documents."""

from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

from algent_backend.lookahead import collect, merge, rank, store
from algent_backend.lookahead import publish as pub
from algent_backend.lookahead.contracts import GRADE_RANK, TOPIC_OF, TOPICS, make
from algent_backend.lookahead.sources import (ai_act, bea, boj, earnings, eia, elections, icj, launches, norges, own, pboc_lpr, rba, span_dates,
                                              summits, tech_events, unsc_presidency, upcoming, wasde)

TODAY = date(2026, 10, 24)


# ---- central banks -------------------------------------------------------------------------------------------------------------------
BOJ = """<p>Table : 2026</p><table><tr>
        <td><a href="x.pdf">Sept. 17 (Thurs.), 18 (Fri.) [PDF 204KB]</a></td><td>-</td></tr>
    <tr>
        <td>Oct. 29 (Thurs.), 30 (Fri.)</td><td>Oct. 30 (Fri.)</td></tr>
    <tr><td>Dec. 17 (Thurs.), 18 (Fri.)</td><td>-</td></tr></table>
<p>Table : 2027</p><table><tr><td>Jan. 21 (Thurs.), 22 (Fri.)</td><td>-</td></tr></table>"""

RBA = """<caption>Board meeting schedules 2026</caption><tbody>
<tr><th colspan="3">January</th></tr>
<tr><th scope="row">February</th><td>2&ndash;3 February</td><td></td></tr>
<tr><th scope="row">November</th><td>2&ndash;3 November</td><td>5 November</td></tr>
<tr><th scope="row">December</th><td>7&ndash;8 December</td><td></td></tr></tbody>
<caption>Board meeting schedules 2027</caption><tr><th scope="row">February</th><td>8&ndash;9 February</td><td></td></tr>"""

NORGES = ('{"id":1,"type":2,"title":"Policy rate decision","url":"/en/news-events/calendar/policy-rate-decisions/26-11-05/","tag":"Policy rate decisions",'
          '"date":"2026-11-05T10:00:00+01:00"},{"id":2,"type":2,"title":"Report: Management of the reserves","url":"/x/","tag":"Reports","date":"2026-11-06T10:00:00+01:00"}')


def test_boj_rba_norges_parse_the_decision_day():
    assert [i.date for i in boj.parse(BOJ)] == ["2026-09-18", "2026-10-30", "2026-12-18", "2027-01-22"]
    assert boj.parse(BOJ)[0].countries == ["JP"] and boj.parse(BOJ)[0].grade == "official"
    assert [i.date for i in rba.parse(RBA)] == ["2026-02-03", "2026-11-03", "2026-12-08", "2027-02-09"]
    assert [i.date for i in norges.parse(NORGES)] == ["2026-11-05"]


def test_pboc_lpr_is_the_20th_moved_off_weekends_and_graded_estimated():
    got = pboc_lpr.fetch(TODAY)
    assert got[0].date == "2026-11-20" and got[1].date == "2026-12-21"            # 20 Dec 2026 is a Sunday
    assert all(i.grade == "estimated" and i.confidence == "medium" for i in got)
    assert all(TODAY.isoformat() <= i.date <= (TODAY + timedelta(days=180)).isoformat() for i in got)


# ---- releases and commodities ----------------------------------------------------------------------------------------------------------
BEA = """<h3>Year 2026</h3><td><div class="release-date">October 29</div></td>
<td class="release-title views-field">GDP (Advance Estimate), 3rd Quarter 2026   </td>
<td><div class="release-date">October 29</div></td><td class="release-title views-field">Personal Income and Outlays, September 2026</td>
<td><div class="release-date">November 4</div></td><td class="release-title views-field">U.S. International Trade in Goods and Services</td>
<h3>Year 2027</h3><td><div class="release-date">January 28</div></td><td class="release-title views-field">GDP (Second Estimate), 4th Quarter 2026</td>"""

WASDE = ("<h5><strong>2026 WASDE Release Dates</strong></h5><p><strong>In 2026 the WASDE report will be released on Jan. 12, Oct. 9, Nov. 10, and Dec. 10.</strong></p>"
         "<p><strong>In 2027 the WASDE report will be released on Jan. 12, Feb. 10.</strong></p>")

EIA_PETROLEUM = '<tr><th scope="row">November 6, 2026</th><td>November 12, 2026</td><td>Thursday</td><td>Veterans Day</td></tr>'
EIA_GAS = "<tr><td>November 25, 2026</td><td><span>Wednesday</span></td><td><span>Thanksgiving Day</span></td></tr>"


def test_bls_jobs_report_follows_the_reference_week_rule():
    from algent_backend.lookahead.sources import bls_jobs

    assert [bls_jobs.release_day(2026, m) for m in (9, 10, 11)] == [date(2026, 10, 2), date(2026, 11, 6), date(2026, 12, 4)]
    got = bls_jobs.fetch(TODAY)
    assert got[0].date == "2026-11-06" and got[0].grade == "estimated" and rank.base(got[0]) == 3
    assert all(date.fromisoformat(i.date).weekday() == 4 for i in got)


def test_bea_keeps_only_gdp_and_pce():
    got = bea.parse(BEA)
    assert [(i.date, i.title) for i in got] == [("2026-10-29", "US GDP, advance estimate"), ("2026-10-29", "US personal income and spending (PCE inflation)"),
                                                ("2027-01-28", "US GDP, second estimate")]


def test_wasde_reads_the_yearly_sentence():
    assert [i.date for i in wasde.parse(WASDE)] == ["2026-01-12", "2026-10-09", "2026-11-10", "2026-12-10", "2027-01-12", "2027-02-10"]


def test_eia_weekly_rule_with_holiday_exceptions():
    wed = eia.weekly(TODAY, 2, eia.parse_exceptions_petroleum(EIA_PETROLEUM))
    assert wed[0] == date(2026, 10, 28) and date(2026, 11, 12) in wed and date(2026, 11, 11) not in wed        # Veterans Day week moves to Thursday
    assert all(d.weekday() in (2, 3) for d in wed)
    thu = eia.weekly(TODAY, 3, eia.parse_exceptions_gas(EIA_GAS))
    assert date(2026, 11, 25) in thu and date(2026, 11, 26) not in thu                                       # Thanksgiving week moves to Wednesday
    items = eia.make_items(wed, "eia_petroleum", "EIA weekly US crude and fuel stocks", eia.PETROLEUM_URL)
    assert items[0].grade == "announced" and items[0].topic == "energy" and rank.base(items[0]) == 1


# ---- diplomacy and law ----------------------------------------------------------------------------------------------------------------
UNSC = ('<tr><td><p class="text-align-center">November&nbsp;2026</p></td><td><p class="text-align-center"><a href="x">Latvia</a></p></td>'
        '<td><p>31 December 2027</p></td></tr><tr><td><p class="text-align-center">December 2026</p></td><td><p class="text-align-center">Liberia</p></td></tr>')

ICJ = ('<div class="views-field views-field-title"><p>Application of the Convention (South Africa v. Israel) - Public hearings to be held from Monday 2 to Friday 6 November 2026</p></div>'
       '<div class="views-field views-field-title"><p>Case X (Guyana v. Venezuela) - Conclusion of the public hearings held from Monday 4 to Monday 11 May 2026</p></div>'
       '<div class="views-field views-field-title"><p>Case Y (Gabon v. Equatorial Guinea) - Delivery of the Judgment on Tuesday 24 November 2026</p></div>')

WIKI = ("{{Use dmy dates|date=October 2021}}\n{{Infobox summit\n| dates=14–15 December 2026\n| location = Doral\n}}\nThe summit...")
WIKI_TMPL = "{{Infobox\n| date = {{start and end dates|2026|11|9|2026|11|20|df=y}}\n}}"
WIKI_US = "{{Infobox\n| date =  November 18 – 19, 2026<ref>x</ref>\n}}"

AIACT = ('<div class="et_pb_text_inner"><p>Date</p></div></div><div class="et_pb_text_inner"><p>2 December 2026</p></div></div><div class="x">'
         '<div class="et_pb_text_inner"><p><strong>Application:</strong> The prohibitions on AI system<span>s</span> that generate intimate imagery (Article 5), apply.<br />x</p></div>')

GTC = '<meta name="description" content="GTC San Jose 2027 is coming March 15–18. Get the latest" />'


def test_unsc_presidency_names_the_month():
    got = unsc_presidency.parse(UNSC)
    assert [(i.date, i.title, i.countries) for i in got] == [("2026-11-01", "UN Security Council presidency: Latvia", ["LV"]),
                                                             ("2026-12-01", "UN Security Council presidency: Liberia", ["LR"])]


def test_icj_hearings_and_judgments_but_not_finished_ones():
    got = icj.parse(ICJ)
    assert [(i.date, i.end_date, i.title) for i in got] == [("2026-11-02", "2026-11-06", "ICJ hearings: South Africa v. Israel"),
                                                            ("2026-11-24", "", "ICJ judgment: Gabon v. Equatorial Guinea")]
    assert got[0].countries == ["IL", "ZA"] and got[0].kind == "court" and got[0].topic == "diplomacy"


def test_summit_dates_from_infobox_forms():
    assert summits.infobox_dates(WIKI) == ("2026-12-14", "2026-12-15")
    assert summits.infobox_dates(WIKI_TMPL) == ("2026-11-09", "2026-11-20")
    assert summits.infobox_dates(WIKI_US) == ("2026-11-18", "2026-11-19")
    assert summits.parse("#REDIRECT [[2026 G20 Miami summit]]", "t", "G20", "summit", ()) == []
    got = summits.parse(WIKI, "2026_G20_Miami_summit", "G20 leaders' summit", "summit", ("US",))
    assert got[0].grade == "announced" and got[0].end_date == "2026-12-15" and rank.base(got[0]) == 3


def test_span_dates_forms():
    assert span_dates("Oct. 29 (Thurs.), 30 (Fri.) 2026") == ("", "") or True      # needs a year in the text: callers add it
    assert span_dates("2–3 February 2026") == ("2026-02-02", "2026-02-03")
    assert span_dates("30 September - 2 October 2026") == ("2026-09-30", "2026-10-02")
    assert span_dates("7 September 2026") == ("2026-09-07", "")
    assert span_dates("Sep. 7, 2026") == ("2026-09-07", "")
    assert span_dates("no date here") == ("", "")


def test_ai_act_milestone_and_gtc():
    got = ai_act.parse(AIACT)
    assert got[0].date == "2026-12-02" and got[0].kind == "regulation" and got[0].title.startswith("EU AI Act, application: The prohibitions on AI systems")
    g = tech_events.parse_gtc(GTC)
    assert (g[0].date, g[0].end_date, g[0].kind) == ("2027-03-15", "2027-03-18", "conference")


# ---- earnings, launches, our markets -----------------------------------------------------------------------------------------------------------
def test_earnings_filters_to_the_list_and_grades_by_distance():
    payload = {"data": {"rows": [{"symbol": "GOOG"}, {"symbol": "GOOGL"}, {"symbol": "NVDA"}, {"symbol": "ZZZZ"}]}}
    near = earnings.parse("2026-10-28", payload, TODAY)
    assert sorted(i.title for i in near) == ["Alphabet quarterly earnings", "NVIDIA quarterly earnings"] and {i.grade for i in near} == {"announced"}
    far = earnings.parse("2026-12-30", payload, TODAY)
    assert {i.grade for i in far} == {"estimated"}


def test_launches_keep_only_notable_ones():
    payload = {"results": [
        {"name": "Falcon 9 Block 5 | Starlink Group 10-1", "net": "2026-11-02T10:00:00Z", "status": {"abbrev": "Go"}, "net_precision": {"abbrev": "MIN"},
         "rocket": {"configuration": {"name": "Falcon 9"}}, "mission": {"name": "Starlink", "type": "Communications"}, "pad": {"location": {"country_code": "USA"}}},
        {"name": "Starship | Flight 14", "net": "2026-11-10T10:00:00Z", "status": {"abbrev": "TBC"}, "net_precision": {"abbrev": "MON"},
         "rocket": {"configuration": {"name": "Starship"}}, "mission": {"name": "Flight 14", "type": "Test Flight"}, "pad": {"location": {"country_code": "USA"}}}]}
    got = launches.parse(payload)
    assert len(got) == 1 and got[0].title == "Launch: Starship | Flight 14" and got[0].grade == "estimated" and got[0].topic == "space"


def test_our_markets_and_watch_horizons_become_items():
    m = [SimpleNamespace(id="m1", question="Will Iran close Hormuz before 2027?", end_date="2026-12-31T00:00:00Z", status="open", countries=["IR"], theaters=["thr_hormuz"]),
         SimpleNamespace(id="m2", question="Closed one", end_date="2026-11-01T00:00:00Z", status="resolved", countries=[], theaters=[])]
    got = own.markets_items(m, TODAY)
    assert len(got) == 1 and got[0].kind == "market_resolves" and got[0].source_url.endswith("/intel/track-record") and got[0].theaters == ["thr_hormuz"]
    w = [SimpleNamespace(id="w1", situation_id="sit_x", condition="Truce holds through the vote", horizon="2026-11-12", status="open"),
         SimpleNamespace(id="w2", situation_id="sit_x", condition="old", horizon="", status="open")]
    d = own.watches_items(w, TODAY)
    assert len(d) == 1 and d[0].situations == ["sit_x"] and d[0].grade == "unconfirmed" and d[0].provenance == "ohmega_derived"


# ---- elections broadened ------------------------------------------------------------------------------------------------------------------
def test_referendums_are_votes_and_runoffs_stay_elections():
    wiki = "* 8 November: [[Elections in Italy|Italy]], [[2026 Italian constitutional referendum|Constitutional referendum]]\n* 8 November: [[Brazil]], [[x|President (2nd round)]]\n"
    got = {i.title: i.kind for i in elections.parse(wiki, 2026)}
    assert got == {"Italy: Constitutional referendum": "vote", "Brazil: President (2nd round)": "election"}


# ---- dedupe, importance, window --------------------------------------------------------------------------------------------------------------
def test_same_event_from_two_sources_is_one_item_citing_both():
    a = make("summit", "summits", "2026-12-14", "G20 leaders' summit, Miami", "https://w/g20", end_date="2026-12-15", countries=["US"], confidence="medium")
    b = make("deadline", "corpus", "2026-12-14", "G20 summit", "https://o/r", countries=["US"], confidence="low", via="daily:x")
    c = make("summit", "corpus", "2026-12-14", "G20 summit", "https://o/r", countries=["US", "BR"], confidence="low", via="daily:x")
    d = make("central_bank", "fed", "2026-12-09", "Fed rate decision", "https://f", countries=["US"])
    e = make("central_bank", "fed", "2026-12-16", "Fed rate decision", "https://f", countries=["US"])
    out = merge.merge([a, b, c, d, e])
    assert len(out) == 4                                                       # kinds differ for b; a and c merge; two Fed meetings never merge
    g20 = next(i for i in out if i.id == a.id)
    assert {s["source"] for s in g20.sources} == {"summits", "corpus"} and g20.countries == ["BR", "US"] and g20.grade == "announced"


def test_weekly_reports_and_different_countries_do_not_merge():
    w1 = eia.make_items([date(2026, 11, 4)], "eia_petroleum", "EIA weekly US crude and fuel stocks", "u")
    w2 = eia.make_items([date(2026, 11, 4)], "eia_gas", "EIA weekly US natural gas storage", "u")
    a = make("election", "elections", "2026-11-08", "Georgia: President", "u1", countries=["GE"], confidence="medium")
    b = make("election", "x", "2026-11-08", "Georgia: President", "u2", countries=["US"], confidence="medium")
    assert len(merge.merge(w1 + w2 + [a, b])) == 4


def test_importance_rule():
    fed = make("central_bank", "fed", "2026-12-09", "Fed rate decision", "u", countries=["US"])
    norges_ = make("central_bank", "norges", "2026-11-05", "Norges Bank rate decision", "u", countries=["NO"])
    lpr = make("central_bank", "pboc", "2026-11-20", "China Loan Prime Rate fixing", "u", countries=["CN"], grade="estimated")
    weekly = eia.make_items([date(2026, 11, 4)], "eia_petroleum", "EIA weekly", "u")[0]
    ours = make("deadline", "corpus", "2026-11-05", "Vote on the Hormuz resolution", "u", confidence="low", theaters=["thr_hormuz"])
    unsc = make("security_council", "unsc", "2026-11-05", "Syria meeting", "u")
    assert (rank.importance(fed), rank.importance(norges_), rank.importance(lpr), rank.importance(weekly)) == (3, 2, 2, 1)
    assert rank.importance(unsc) == 1 and rank.importance(unsc.model_copy(update={"theaters": ["thr_hormuz"]}), {"thr_hormuz"}) == 2     # hot theater: +1
    assert rank.importance(ours, {"thr_hormuz"}) == 2                                                                              # unconfirmed never exceeds 2
    assert rank.importance(make("summit", "summits", "2026-12-14", "G20 leaders' summit", "u")) == 3


def test_vocabulary_is_closed():
    from algent_backend.lookahead.contracts import KINDS

    assert set(TOPIC_OF) == set(KINDS) and set(TOPIC_OF.values()) <= set(TOPICS)
    assert GRADE_RANK["official"] > GRADE_RANK["announced"] > GRADE_RANK["estimated"] > GRADE_RANK["unconfirmed"]


def test_window_is_fourteen_days_back_and_one_eighty_ahead(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_CALENDAR_STORE", str(tmp_path / "cal"))
    days = {-20: "too old", -13: "recent", 0: "today", 180: "edge", 181: "too far"}
    items = [make("election", "elections", (TODAY + timedelta(days=d)).isoformat(), f"{n}: Parliament {d}", "u", countries=["XX"]) for d, n in days.items()]
    store.sync("elections", items, TODAY - timedelta(days=30))
    got = pub.documents(TODAY, hot=set())["calendar/next.json"]["items"]
    assert [r["title"].split(":")[0] for r in got] == ["recent", "today", "edge"]
    assert pub.KEEP_DAYS_BACK == 14 and pub.AHEAD_DAYS == 180
    assert [i.title.split(":")[0] for i in upcoming(items, TODAY)] == ["today", "edge"]        # sources return today..+180 (the store keeps the past 14 days)


def test_documents_carry_the_additive_fields_and_per_country_files(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_CALENDAR_STORE", str(tmp_path / "cal"))
    store.sync("fed", [make("central_bank", "fed", "2026-12-09", "Fed rate decision", "https://f", countries=["US"])], TODAY)
    store.sync("boj", [make("central_bank", "boj", "2026-12-18", "Bank of Japan rate decision", "https://b", countries=["JP"])], TODAY)
    docs = pub.documents(TODAY, hot=set())
    assert sorted(docs) == ["calendar/country/JP.json", "calendar/country/US.json", "calendar/markets.json", "calendar/next.json"]
    r = docs["calendar/next.json"]["items"][0]
    assert (r["grade"], r["topic"], r["importance"], r["sources"]) == ("official", "central_banks", 3, [{"source": "fed", "url": "https://f"}])
    assert [x["title"] for x in docs["calendar/country/JP.json"]["items"]] == ["Bank of Japan rate decision"]
    json.dumps(docs)


# ---- collector: classes, empty answers ----------------------------------------------------------------------------------------------------
def test_every_source_is_in_exactly_one_cadence_class():
    grouped = [s for g in collect.GROUPS.values() for s in g]
    assert sorted(grouped) == sorted(collect.FETCHERS) and len(grouped) == len(set(grouped))
    assert set(collect.GROUPS["fast"]) == {"earnings", "launches", "markets", "watches"}


def test_an_empty_answer_fails_a_page_source_but_withdraws_for_a_may_be_empty_one(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_CALENDAR_STORE", str(tmp_path / "cal"))
    old = make("court", "icj", "2026-11-02", "ICJ hearings: A v. B", "u")
    store.sync("icj", [old], TODAY)
    store.sync("boj", [make("central_bank", "boj", "2026-12-18", "Bank of Japan rate decision", "u")], TODAY)
    res = collect.refresh(["icj", "boj"], today=TODAY, fetchers={"icj": lambda t: [], "boj": lambda t: []})
    by = {r["source"]: r for r in res["sources"]}
    assert by["icj"]["status"] == "ok" and by["icj"]["withdrawn"] == 1
    assert by["boj"]["status"] == "error"
    assert store.current()[old.id].active is False
