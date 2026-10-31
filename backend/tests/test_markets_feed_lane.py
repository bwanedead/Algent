"""The bot's feed lane (research.feed_lane, day_tools search/about): a structured feed row surfaces beside news, deduped, labelled, and never for research or unknowable asks."""

from __future__ import annotations

from datetime import UTC, date, datetime

from algent_backend.markets import day_tools, flags, research
from algent_backend.markets.day_prompt import Call

TODAY = date(2026, 10, 31)
NEWS = [{"id": f"daily:{i}", "kind": "daily", "date": "2026-10-30", "title": f"Rates news {i}"} for i in range(3)]
CAL = [{"id": "cal:boc", "kind": "calendar", "date": "2026-12-09", "title": "Bank of Canada rate decision", "product": "calendar"},
       {"id": "daily:0", "kind": "daily", "date": "2026-10-30", "title": "Rates news 0", "product": "calendar"},
       {"id": "market:x", "product": "markets", "title": "price"}]


class FakeCorpus:
    """Unrestricted search returns only news; ``products`` restricts to the feed. Records every call."""

    def __init__(self):
        self.calls = []

    def search(self, text, *, products=None, **kw):
        self.calls.append({"products": products, **kw})
        return list(CAL if products else NEWS)


def session(corpus):
    return day_tools.Session(now=datetime(2026, 10, 31, 12, tzinfo=UTC), get=lambda *a, **k: None, corpus=corpus)


def test_a_schedule_ask_returns_calendar_hits_the_news_search_misses():
    c = FakeCorpus()
    hits = research.feed_lane(c, "Bank of Canada rate decision meeting scheduled", today=TODAY)
    assert [h.id for h in hits] == ["cal:boc", "daily:0"]                    # the markets row is blinded
    assert "from the calendar" in hits[0].text
    assert c.calls[0]["products"] == {"calendar"} and "until" not in c.calls[0]      # a future-dated item is not cut off
    assert c.calls[0]["since"] == "2026-07-03"


def test_unknowable_research_and_actor_routes_return_nothing():
    c = FakeCorpus()
    assert research.feed_lane(c, "US strikes on Iran Nov 20", today=TODAY) == []     # an event dated after today
    assert research.feed_lane(c, "Ukraine grain corridor", today=TODAY) == []        # no feed: research
    assert research.feed_lane(c, "current head of state in Iran", today=TODAY) == [] # actors: the entity tool
    assert c.calls == []


def test_the_tool_appends_the_lane_deduped_under_a_header_and_cites_it():
    s = session(FakeCorpus())
    out = s.run(1, Call(tool="search", query="Bank of Canada rate decision meeting scheduled")).result
    assert out.count("daily:0") == 1 and "— from the calendar —" in out and "cal:boc" in out
    assert "cal:boc" in s.shown
    assert "from the" not in s.run(1, Call(tool="timeline", query="Bank of Canada rate decision meeting scheduled")).result      # search and about only


def test_flag_off_means_no_lane(monkeypatch):
    monkeypatch.setattr(flags, "SEARCH_FEED_LANE", False)
    assert "cal:boc" not in session(FakeCorpus()).run(1, Call(tool="search", query="Bank of Canada rate decision meeting scheduled")).result
