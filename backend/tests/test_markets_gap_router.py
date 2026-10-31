"""The gap router (markets/gap_router.py): the kind rules on real asks, the routes, the unknowable date cue, the retrieval-vs-coverage probe (a fake corpus and a
real product-restricted search), the fill skipping what a free feed answers, and the published block. No model call; nothing touches the network."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from algent_backend.corpus import schema
from algent_backend.corpus.query import Corpus
from algent_backend.corpus.sink import Sink
from algent_backend.markets import flags, gap_router, gaps, research_report, store
from algent_backend.markets.contracts import Gap
from algent_backend.ops.products import views

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)

#: Live asks sampled from the gap ledger (10-30): topic -> kind.
ASKS = {
    "Likud seat projections Oct 27": "poll", "Senate generic ballot": "poll", "Brazil runoff final polls": "poll", "Georgia gubernatorial polling": "poll",
    "Bulgarian CEC results": "result", "TSE vote count": "result", "Brazil election official results": "result",
    "Saudi strike on Yemen Oct 29": "event", "US strikes on Iran Oct 25": "event",
    "Trump-Putin meeting confirmed": "schedule", "Araghchi statements on enrichment": "statement",
    "IMF Portwatch Hormuz arrivals": "series", "current head of state in Iran": "status", "Ukraine grain corridor": "other",
}


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "ms"))
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path / "no-profiles"))
    monkeypatch.setattr("algent_backend.markets.research.open_corpus", lambda: None)      # no index unless a test hands one in


def ask(topic, market="m1", days=1.0, why="", question=""):
    at = (NOW - timedelta(days=days)).isoformat(timespec="seconds")
    store.append_gaps([Gap(id=f"g-{market}-{topic[:12]}", at=at, day=at[:10], topic=topic, why=why, market_id=market, question=question)])


@pytest.mark.parametrize(("topic", "kind"), ASKS.items())
def test_real_asks_land_in_their_kind(topic, kind):
    assert gap_router.classify(topic) == kind


def test_the_topic_outranks_the_why_and_the_market_question():
    assert gap_router.classify("Likud seat projections", why="whether Netanyahu will say", question="Will Israel strike Iran?") == "poll"
    assert gap_router.classify("Ukraine grain corridor", why="", question="Will Russia strike Odesa?") == "event"      # nothing in the topic: the question breaks the tie
    assert gap_router.classify("") == "other"


def test_every_kind_routes_to_a_registered_product_or_research():
    products = {p.id for p in views.products()}
    assert set(gap_router.KINDS) == {*gap_router.FEEDS, "other"}
    assert set(gap_router.FEEDS.values()) - {"elections"} <= products
    assert gap_router.route_of("poll") == "feed:elections" == gap_router.route_of("result")
    assert gap_router.route_of("other") == "research"
    assert gap_router.route_of("series", "dark fleet AIS gaps near Hormuz") == "feed:maritime" and "maritime" in products
    assert gap_router.route_of("series", "Hormuz arrivals") == "feed:instruments"


def test_date_cues_and_what_cannot_be_known_yet():
    today = NOW.date()
    assert sorted(gap_router.cue_dates("Oct 29 and 2026-11-05 and 7 Nov 2026", today)) == [date(2026, 10, 29), date(2026, 11, 5), date(2026, 11, 7)]
    assert gap_router.cue_dates("it may happen", today) == []
    assert gap_router.cue_dates("Jan 5", today) == [date(2027, 1, 5)]                           # no year, long gone this year: next year's
    assert gap_router.unknowable("result", "Final certified count Nov 5", today)               # the vote is still ahead
    assert gap_router.unknowable("event", "Saudi strike on Yemen Nov 3", today)
    assert not gap_router.unknowable("event", "Saudi strike on Yemen Oct 29", today)           # past: knowable
    assert not gap_router.unknowable("poll", "Final polls Nov 3", today)                       # polls before a coming vote are knowable
    assert not gap_router.unknowable("result", "Bulgarian CEC results", today)                 # no date cue: not decided on a guess


class FakeCorpus:
    """Holds what ``books`` says: product -> list of (title, snippet) for search, entity names with instrument series, and countries with leaders."""

    def __init__(self, books=None, series=(), leaders=()):
        self.books, self.series_of, self.leaders = books or {}, set(series), set(leaders)
        self.closed = False

    def search(self, text, *, products=None, limit=10, **_):
        return [{"title": t, "snippet": s} for p in (products or ()) for t, s in self.books.get(p, [])][:limit]

    def series(self, name, **_):
        return [{"product": "instruments"}] if name in self.series_of else []

    def entity(self, name):
        return {"latest": {"leaders": [{"name": "x"}]}} if name in self.leaders else None

    def close(self):
        self.closed = True


def routed(topic, corpus, why="", asks=1, question=""):
    ask(topic, why=why, question=question)
    c = next(c for c in gaps.clusters(NOW) if c.topic == topic)
    c.asks = asks
    return gap_router.route_clusters([c], NOW, corpus)[0]


def test_a_feed_that_holds_the_ask_is_a_retrieval_miss_and_one_that_does_not_is_a_coverage_miss():
    held = FakeCorpus({"statements": [("Araghchi on enrichment", "Iran will keep enrichment rights, Araghchi said")]})
    r = routed("Araghchi statements on enrichment", held)
    assert (r.kind, r.route, r.diagnosis, r.held) == ("statement", "feed:statements", "retrieval_miss", 1)
    assert r.skip_reason() and "did not find" in r.skip_reason()
    r = routed("Araghchi statements on enrichment", FakeCorpus({"statements": [("Lavrov on Ukraine", "talks continue")]}))
    assert r.diagnosis == "coverage_miss" and r.skip_reason() == ""                              # a word in common is not enough: the ask must be there
    assert routed("Araghchi statements on enrichment", FakeCorpus()).diagnosis == "coverage_miss"


def test_numbers_and_leaders_are_found_through_the_names_in_the_ask():
    assert routed("IMF Portwatch Hormuz arrivals", FakeCorpus(series=["Hormuz"])).diagnosis == "retrieval_miss"
    assert routed("IMF Portwatch Hormuz arrivals", FakeCorpus()).diagnosis == "coverage_miss"
    assert routed("current head of state in Iran", FakeCorpus(leaders=["Iran"])).diagnosis == "retrieval_miss"


def test_no_index_or_a_broken_one_leaves_the_probe_unchecked_and_never_raises():
    assert routed("Araghchi statements on enrichment", None).diagnosis == ""

    class Broken(FakeCorpus):
        def search(self, *a, **k):
            raise RuntimeError("database disk image is malformed")

    assert routed("Araghchi statements on enrichment", Broken()).diagnosis == ""


def test_probes_are_bounded_per_pass(monkeypatch):
    monkeypatch.setattr(flags, "GAP_ROUTE_MAX_PROBES", 2)
    for i, w in enumerate(("alpha", "bravo", "charlie")):
        ask(f"{w} statements on enrichment", market=f"m{i}")
    got = gap_router.route_clusters(gaps.clusters(NOW), NOW, FakeCorpus())
    assert sorted(r.diagnosis for r in got) == ["", "coverage_miss", "coverage_miss"]


def test_a_corpus_it_opened_itself_is_closed(monkeypatch):
    fake = FakeCorpus()
    monkeypatch.setattr("algent_backend.markets.research.open_corpus", lambda: fake)
    ask("Araghchi statements on enrichment")
    gap_router.route_clusters(gaps.clusters(NOW), NOW)
    assert fake.closed


def test_elections_unknowable_and_retrieval_misses_are_not_paid_for():
    assert routed("Senate generic ballot", None).skip_reason() == "the free elections feed answers polls and results"
    assert "cannot be known yet" in routed("Final certified count Nov 5", None, why="official result").skip_reason()
    assert routed("Ukraine grain corridor", None).skip_reason() == ""                           # research stays research
    assert routed("Saudi strike on Yemen Oct 29", None).skip_reason() == ""                     # a feed route not proven held is still researched


def test_fill_skips_what_a_free_feed_answers_without_spending_a_cap(monkeypatch):
    for i, t in enumerate(("Senate generic ballot", "Final certified count Nov 5", "Ukraine grain corridor shipments")):
        ask(t, market=f"m{i}", days=1)
    ran = []
    out = gaps.fill(now=NOW, runner=lambda t, w: ran.append(t) or {"ok": True}, limit=2)
    assert ran == ["Ukraine grain corridor shipments"] and out["ran"] == 1
    assert {s["topic"] for s in out["skipped"]} == {"Senate generic ballot", "Final certified count Nov 5"}
    assert all(s["reason"] for s in out["skipped"]) and out["candidates"] == 1


def test_the_switch_restores_the_old_behaviour(monkeypatch):
    monkeypatch.setattr(flags, "GAP_ROUTE_SKIP_FILLS", False)
    ask("Senate generic ballot")
    ran = []
    out = gaps.fill(now=NOW, runner=lambda t, w: ran.append(t) or {"ok": True})
    assert ran == ["Senate generic ballot"] and "skipped" not in out


def test_the_block_counts_asks_by_kind_route_and_miss_and_lists_wanted_feeds():
    for i, (t, n) in enumerate((("Senate generic ballot", 3), ("Araghchi statements on enrichment", 2), ("Ukraine grain corridor", 1), ("Final certified count Nov 5", 1))):
        for j in range(n):
            ask(t, market=f"m{i}{j}")
    corpus = FakeCorpus({"statements": [("Araghchi on enrichment", "Araghchi statements on enrichment today")]})
    b = gap_router.block(NOW, gap_router.route_clusters(gaps.clusters(NOW), NOW, corpus))
    assert (b["asks"], b["clusters"]) == (7, 4)
    assert (b["held_missed"], b["not_held"], b["no_feed"], b["unknowable"]) == (2, 3, 1, 1)
    by = {(r["kind"], r["route"]): r for r in b["rows"]}
    assert by[("poll", "feed:elections")]["not_held"] == 3 and by[("statement", "feed:statements")]["held_missed"] == 2
    assert by[("poll", "feed:elections")]["route_label"] == "elections feed" and by[("other", "research")]["route_label"] == "a paid research run"
    assert [(w["kind"], w["asks"]) for w in b["wanted"]] == [("poll", 3), ("other", 1)]         # not held on a feed, or no feed at all; never the unknowable
    assert "ballot" in b["wanted"][0]["topics"][0] and b["basis"]
    assert "poll" in gap_router.table(b) and "wanted feeds" in gap_router.table(b)


def test_the_evidence_section_publishes_the_routing_block():
    ask("Senate generic ballot")
    sec = research_report.section([], NOW)
    assert sec["routing"]["rows"][0]["kind"] == "poll"


def test_search_can_be_restricted_to_a_product(tmp_path):
    path = tmp_path / "corpus.db"
    db = schema.connect(path, write=True)
    schema.create(db)
    for product, doc in (("elections", "election:il:avg:2026-10-27"), ("dailies", "daily:geopolitics:2026-10-27")):
        Sink(db, product, doc, "2026-10-27T00:00:00+00:00").document(doc, "x", date="2026-10-27", title="Likud seat projections", body="Likud 31 seats in the polls")
    db.commit()
    db.close()
    with Corpus.open(tmp_path) as c:
        assert len(c.search("Likud seat projections")) == 2
        assert [r["product"] for r in c.search("Likud seat projections", products={"elections"})] == ["elections"]
        assert gap_router.held(c, "elections", "Likud seat projections Oct 27") == 1
        assert gap_router.held(c, "conflict", "Likud seat projections Oct 27") == 0
