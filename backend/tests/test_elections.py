"""The elections feed (elections/): the wikitext table reader on saved fragments (spans, templates, refs), the poll and results extractors, the recent average, the
status words, target selection from the calendar and from asks, the append-only store, the corpus adapter and the registry entry. Fetching is injected: no network."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest

from algent_backend.corpus.build import build
from algent_backend.corpus.query import Corpus
from algent_backend.elections import collect, country, flags, polls, results, store, wikitext
from algent_backend.elections.contracts import Snapshot
from algent_backend.lookahead.sources import elections as calendar_page
from algent_backend.ops.products import validate, views

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "elections"
TODAY = date(2026, 10, 31)
NOW = datetime(2026, 10, 31, 1, 50, tzinfo=UTC)
HU, IL = "2026 Hungarian parliamentary election", "2026 Israeli legislative election"


def fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_ELECTIONS_STORE", str(tmp_path / "es"))


def served(pages: dict[str, str], calendar: str = "", search: list[str] | None = None, log: list[str] | None = None):
    """A fake ``Fetch``: calendar pages by year, articles by title, and the search API."""
    def fetch(url: str) -> str:
        if log is not None:
            log.append(url)
        if "national_electoral_calendar" in url:
            return calendar if "2026_national" in url else ""
        if "api.php" in url:
            return json.dumps({"query": {"search": [{"title": t} for t in (search or [])]}})
        title = unquote(parse_qs(urlparse(url).query)["title"][0]).replace("_", " ")
        return pages.get(title, "")
    return fetch


# ── wikitext ──────────────────────────────────────────────────────────────────────────────────────
def test_clean_keeps_link_labels_and_template_text_and_drops_refs_and_files():
    raw = "[[File:x.png|20px]] '''[[Tisza Party|Tisza]]'''<ref name=a>cite</ref> {{small|{{nowrap|12.3}}}}{{party shading/Fidesz}} &nbsp;%<!-- c -->"
    assert wikitext.clean(raw) == "Tisza 12.3 %"
    assert wikitext.clean("{{sort|0123|Channel 12}}") == "Channel 12"


def test_a_table_is_a_grid_with_spans_and_the_heading_above_it():
    t = wikitext.tables("== A ==\ntext\n=== Seats ===\n{|\n|+ Cap\n! rowspan=2 | X !! colspan=2 | Y\n|-\n! a !! b\n|-\n| 1 || 2 || 3\n|}\n")[0]
    assert (t.heading, t.caption) == ("Seats", "Cap")
    g = wikitext.grid(t.rows)
    n = wikitext.header_rows(g)
    assert n == 2 and wikitext.column_names(g, n) == ["X", "Y a", "Y b"]
    assert [c.text for c in g[2]] == ["1", "2", "3"]


def test_a_malformed_row_gives_fewer_cells_and_never_raises():
    t = wikitext.tables("{|\n! A !! B\n|-\n| only one\n|-\n|\n|}")[0]
    assert [[c.text for c in r] for r in wikitext.grid(t.rows)] == [["A", "B"], ["only one"], [""]]


# ── polls ─────────────────────────────────────────────────────────────────────────────────────────
def test_percent_polls_with_two_header_rows_refs_templates_and_a_previous_election_row():
    tables = polls.extract(fx("poll_percent.wiki"), 2026)
    main = tables[0]
    assert (main.heading, main.unit, main.n_total) == ("Party polling", "percent", 6)       # the 2022 election row is not a poll
    newest = main.polls[0]
    assert (newest.pollster, newest.date, newest.sample) == ("Medián", "2026-10-28", 1000)
    assert newest.shares == {"Fidesz": 38.0, "Tisza": 47.0, "MH": 6.0, "DK": 3.0} and newest.others == {"Others": 6.0, "Lead": 9.0}
    publicus = next(p for p in main.polls if p.pollster == "Publicus")
    assert publicus.shares["Fidesz"] == 41.0 and publicus.sample == 1200 and not publicus.uncertain
    assert next(p for p in main.polls if p.date == "2026-10-02").pollster == "Republikon Institute"      # "20 Sep – 2 Oct 2026" ends 2 Oct


def test_a_row_that_does_not_parse_is_kept_as_raw_cells_not_dropped_or_guessed():
    bad = next(p for p in polls.extract(fx("poll_percent.wiki"), 2026)[0].polls if p.pollster == "Unclear Pollster")
    assert bad.uncertain and bad.shares == {} and bad.date == "" and bad.raw[:2] == ["Unclear Pollster", "fieldwork unclear"]


def test_the_average_is_the_mean_of_the_newest_five_readable_polls():
    avg = polls.extract(fx("poll_percent.wiki"), 2026)[0].average
    assert (avg.n_polls, avg.first, avg.last) == (5, "2026-10-02", "2026-10-28")
    assert avg.shares == {"Fidesz": 40.0, "Tisza": 44.6, "MH": 6.0, "DK": 3.6}               # no Others, no Lead: those are not parties
    assert avg.pollsters[0] == "Medián" and "Unclear Pollster" not in avg.pollsters


def test_a_party_missing_from_some_polls_is_averaged_over_the_polls_that_carry_it():
    rows = [polls.Poll(pollster="a", date="2026-10-02", shares={"X": 10.0, "Y": 20.0}), polls.Poll(pollster="b", date="2026-10-03", shares={"X": 20.0})]
    assert polls.average(rows).shares == {"X": 15.0, "Y": 20.0}
    assert polls.average([]) is None and polls.average([polls.Poll(pollster="u", uncertain=True)]) is None


def test_seat_projections_read_as_seats_and_dates_inherit_the_year_band():
    t = polls.extract(fx("poll_seats.wiki"), 2026)[0]
    assert t.unit == "seats" and t.n_total == 6
    assert [p.date for p in t.polls] == ["2026-10-26", "2026-10-25", "2026-10-23", "2026-10-22", "2026-10-20", "2025-12-30"]
    assert t.polls[0].shares["Likud"] == 32.0 and t.polls[0].others == {"Others": 39.0}
    assert t.average.shares["Likud"] == 32.0 and t.average.unit == "seats" and t.average.n_polls == 5      # the 2025 poll is the sixth


def test_numbers_are_read_defensively():
    assert [polls.number(x) for x in ("32.5", "32,5 %", "31 seats", "1,234", "<1", "–", "", "n/a")] == [32.5, 32.5, 31.0, None, None, None, None, None]


# ── results ───────────────────────────────────────────────────────────────────────────────────────
def test_a_party_results_table_with_votes_percent_seats_and_totals():
    r = results.extract(fx("results_preliminary.wiki"))
    assert r.heading == "Results" and r.status == "preliminary" and "preliminary" in r.status_note
    top = r.rows[0]
    assert (top.name, top.votes, top.percent, top.seats) == ("Tisza Party", 2845201, 49.1, 98)
    assert [x.name for x in r.rows] == ["Tisza Party", "Fidesz–KDNP", "Our Homeland Movement", "Others"]
    assert r.totals["total"] == 5796916.0 and r.totals["valid votes"] == 5796916.0 and "invalid/blank votes" in r.totals


def test_a_candidate_table_names_the_person_and_the_party_and_reads_the_certification():
    r = results.extract(fx("results_candidates.wiki"))
    assert r.status == "official" and "official" in r.status_note
    assert [(x.name, x.party, x.votes, x.percent) for x in r.rows] == [("Ana Silva", "SP", 52310442, 50.8), ("Bruno Costa", "LU", 50100331, 48.7)]
    assert r.totals["blank votes"] == 520100.0


def test_status_is_unstated_when_the_page_says_neither_and_polls_are_not_results():
    assert results.status_of("The party won 40 seats.") == ("unstated", "")
    assert results.status_of("with 96.3% of votes counted")[0] == "preliminary"
    assert results.extract(fx("poll_percent.wiki")) is None and results.extract("no tables here") is None


# ── targets ───────────────────────────────────────────────────────────────────────────────────────
def test_calendar_pages_give_each_election_its_article_title():
    got = {i.title: page for i, page in calendar_page.parse_with_pages(fx("calendar_2026.wiki"), 2026)}
    assert got["Latvia: Parliament"] == "2026 Latvian parliamentary election" and got["Brazil: President (2nd round)"] == ""
    assert got["United States: Senate"] == "2026 United States Senate elections"
    assert [i.title for i in calendar_page.parse(fx("calendar_2026.wiki"), 2026)][0] == "Latvia: Parliament"          # parse is unchanged


def test_targets_are_the_calendar_elections_in_the_window_with_an_article_nearest_first():
    ts = collect.calendar_targets(TODAY, served({}, fx("calendar_2026.wiki")))
    assert [t.title for t in ts] == ["2026 United States Senate elections", IL, "2026 Bulgarian presidential election", "2026 Latvian parliamentary election",
                                     "2026 Nowhere general election", "2026 Chilean general election"]
    assert ts[1].country == "IL" and ts[1].date == "2026-10-27"
    assert len(collect.calendar_targets(date(2026, 3, 1), served({}, fx("calendar_2026.wiki")))) == 0                   # nothing near in March


def test_the_cap_bounds_the_elections_read(monkeypatch):
    monkeypatch.setattr(flags, "MAX_ELECTIONS", 2)
    assert len(collect.calendar_targets(TODAY, served({}, fx("calendar_2026.wiki")))) == 2


def test_asks_already_covered_by_the_calendar_cost_no_search_and_new_ones_cost_one_each(monkeypatch):
    known = collect.calendar_targets(TODAY, served({}, fx("calendar_2026.wiki")))
    log: list[str] = []
    fetch = served({}, search=["Opinion polling for the 2026 Georgia gubernatorial election", "2026 Georgia gubernatorial election"], log=log)
    got = collect.ask_targets(["Bulgarian CEC results", "Georgia gubernatorial polling", "Senate generic ballot"], known, fetch)
    assert [(t.title, t.via, t.asked) for t in got] == [("2026 Georgia gubernatorial election", "ask", "Georgia gubernatorial polling")]
    assert len([u for u in log if "api.php" in u]) == 1 and "gubernatorial" in log[0]            # Bulgaria and Senate are on the calendar: no search
    monkeypatch.setattr(flags, "MAX_ASK_SEARCHES", 1)
    log.clear()
    collect.ask_targets(["Alpha vote count", "Bravo vote count"], [], served({}, search=[], log=log))
    assert len(log) == 1
    assert collect.ask_targets(["Alpha vote count"], [], served({}, search=["Something else"])) == []                    # a search that finds no election adds none


def test_the_country_comes_from_the_title_even_as_a_demonym():
    assert [country.of(t) for t in (HU, IL, "2026 Brazilian general election", "2026 Georgia gubernatorial election", "2026 United States Senate elections",
                                    "2026 Czech parliamentary election", "2026 Nigerien election", "Opinion x")] == ["HU", "IL", "BR", "US", "US", "CZ", "", ""]


# ── snapshot, store, run ──────────────────────────────────────────────────────────────────────────
PAGES = {f"Opinion polling for the {HU}": fx("poll_percent.wiki"), HU: fx("results_preliminary.wiki"),
         f"Opinion polling for the {IL}": fx("poll_seats.wiki")}


def test_a_snapshot_carries_polls_average_results_pages_and_the_licence():
    s = collect.snapshot(collect.Target(HU), served(PAGES), "2026-10-31T01:50:00+00:00")
    assert [t.heading for t in s.polls] == ["Party polling", "Hypothetical polling"] and s.polls[0].average.shares["Tisza"] == 44.6
    assert s.results.status == "preliminary" and s.country == "HU" and s.confidence == "medium" and s.license == "CC BY-SA 4.0"
    assert s.pages == {"polling": "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Hungarian_parliamentary_election",
                       "election": "https://en.wikipedia.org/wiki/2026_Hungarian_parliamentary_election"}
    assert collect.snapshot(collect.Target("2030 Nowhere election"), served(PAGES)) is None


def test_a_redirect_is_followed_once_and_an_election_page_without_a_polling_page_still_yields_its_own_tables():
    fetch = served({"Short": "#REDIRECT [[Long title]]", "Long title": "text"})
    assert collect.read_page(fetch, "Short") == "text"
    only = collect.snapshot(collect.Target(HU), served({HU: fx("results_preliminary.wiki") + fx("poll_percent.wiki")}), "t")
    assert only.polls and only.results and "polling" not in only.pages


def test_the_store_is_append_only_and_an_unchanged_read_adds_nothing():
    a = collect.snapshot(collect.Target(HU), served(PAGES), "2026-10-30T01:50:00+00:00")
    b = a.model_copy(update={"acquired_at": "2026-10-31T01:50:00+00:00"})
    assert store.append(a) and not store.append(b)                                            # same content, a day later: no new line
    changed = a.model_copy(update={"acquired_at": "2026-11-01T01:50:00+00:00", "results": None})
    assert store.append(changed)
    got = store.snapshots(a.slug)
    assert [s.acquired_at[:10] for s in got] == ["2026-10-30", "2026-11-01"] and got[0].results is not None      # history is kept, never overwritten
    assert store.latest(a.slug).results is None and store.slugs() == [a.slug]
    p = store.root() / "snapshots" / f"{a.slug}.jsonl"
    p.write_text(p.read_text(encoding="utf-8") + "{torn\n", encoding="utf-8")
    assert len(store.snapshots(a.slug)) == 2                                                  # a torn line hides nothing


def test_a_run_reads_the_calendar_elections_and_a_second_run_changes_nothing():
    fetch = served(PAGES, fx("calendar_2026.wiki"))
    r = collect.run(today=TODAY, fetch=fetch, now=NOW)
    assert r["errors"] == [] and r["appended"] == 1 and len(r["elections"]) == 6          # six on the calendar, only Israel has pages we can read
    assert [e["election"] for e in r["elections"] if e["appended"]] == [IL]
    assert collect.run(today=TODAY, fetch=fetch, now=NOW)["appended"] == 0
    st = store.load_status()
    assert st["last_ok"] == "2026-10-31T01:50:00+00:00" and st["appended"] == 0 and st["elections"] == 6


def test_a_failing_page_is_one_error_and_the_rest_still_run():
    def fetch(url: str) -> str:
        if "Israeli" in url:
            raise collect.polite_http.SourceError("boom")
        return served(PAGES, fx("calendar_2026.wiki"))(url)

    r = collect.run(today=TODAY, fetch=fetch, now=NOW)
    assert r["errors"] and "boom" in r["errors"][0]


# ── corpus adapter ────────────────────────────────────────────────────────────────────────────────
def test_the_adapter_lands_averages_polls_and_results_as_citable_documents(tmp_path, monkeypatch):
    for env, name in {"ALGENT_CORPUS_STORE": "corpus", "ALGENT_ACTORS_STORE": "actors"}.items():
        monkeypatch.setenv(env, str(tmp_path / name))
    fetch = served(PAGES, fx("calendar_2026.wiki"))
    collect.run(today=TODAY, fetch=fetch, now=NOW)
    store.append(collect.snapshot(collect.Target(HU, "HU", "2026-04-12"), fetch, "2026-10-31T01:50:00+00:00"))
    build(only=["actors", "elections"], full=True)
    with Corpus.open() as c:
        ids = {r["id"] for r in c.search("Hungarian polling average", limit=30)}
        assert "election:2026-hungarian-parliamentary-election:avg:2026-10-31" in ids
        poll = c.search("Medián poll Hungarian", kinds={"election_poll"})[0]
        assert poll["id"] == "election:2026-hungarian-parliamentary-election:poll:2026-10-28:median" and "wikipedia.org" in poll["url"] and poll["product"] == "elections"
        res = c.search("Hungarian parliamentary election results Tisza", kinds={"election_result"})[0]
        assert res["id"].endswith(":result:2026-10-31")
        assert c.search("Likud seat projections", products={"elections"})
        hu = c.about("Hungary")
        assert {d["kind"] for d in hu["documents"]} >= {"election_poll_average", "election_poll", "election_result"}
        assert c.entity("Tisza") is not None and c.about("Tisza")["documents"]
        s = c.series("election.avg.2026-hungarian-parliamentary-election", limit=10)
        assert s and s[0]["basis"] == "our_derived" and s[0]["product"] == "elections"


# ── the product registry ──────────────────────────────────────────────────────────────────────────
def test_the_registry_entry_is_valid_free_corpus_only_and_backed_up():
    p = views.by_id("elections")
    assert validate.validate() == []
    assert p.publishes == () and p.site_routes == () and p.irreplaceable and p.stores[0].backed_up        # corpus-only: no R2 documents
    job = p.job_list()[0]
    assert job.spend == "free" and job.argv == ("elections", "run") and job.when().startswith("*-*-* 01:50")
    assert "elections_store" in views.backup_sources()
