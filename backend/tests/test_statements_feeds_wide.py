"""The wider feed table — parsers against real captured fixtures, mocked HTTP, no model."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from algent_backend.agent_system.agents.statements import collect, store
from algent_backend.agent_system.agents.statements.sources import SOURCES, by_id

FIX = Path(__file__).parent / "fixtures" / "statements"
NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def _entries(feed_id: str, fixture: str):
    src = by_id(feed_id)
    payload = (FIX / fixture).read_bytes()
    if src.kind == "listing":
        return collect.parse_listing(payload, src)
    if src.kind == "json":
        return collect.JSON_PARSERS[src.parser](payload, src)
    return collect.parse_feed(payload)


def test_catalog_ids_are_unique_and_json_sources_have_parsers() -> None:
    ids = [s.id for s in SOURCES]
    assert len(ids) == len(set(ids))
    assert all(s.parser in collect.JSON_PARSERS for s in SOURCES if s.kind == "json")
    assert all(s.link_pattern for s in SOURCES if s.kind == "listing")


def test_nato_json_listing_titles_and_dates_from_link() -> None:
    es = _entries("nato_transcripts", "nato_transcripts.json")
    assert len(es) == 4 and all(e.url.startswith("https://www.nato.int/en/news-and-events/events/transcripts/") for e in es)
    assert es[0].published == "2026-10-01" and "Secretary General" in es[0].title


def test_elysee_feed_dates_and_dead_en_links_are_rewritten(tmp_path) -> None:
    src = by_id("elysee")
    assert all(e.published.startswith("2026-") for e in _entries("elysee", "elysee.xml"))
    got = []
    collect.collect_source(src, root=tmp_path, now=NOW, sleep=lambda _s: None,
                           http_get=lambda u: (FIX / "elysee.xml").read_bytes(),
                           read_page=lambda u: got.append(u) or "Le Président a déclaré une chose. " * 20)
    assert got and all("/en/emmanuel-macron/" not in u and "/emmanuel-macron/" in u for u in got)
    assert all(store.load_transcript(t, tmp_path).language == "fr" for t in store.transcript_ids(tmp_path))


@pytest.mark.parametrize("feed_id,fixture,prefix", [
    ("auswaertiges_amt", "auswaertiges_listing.html", "https://www.auswaertiges-amt.de/en/newsroom/news/"),
    ("tccb", "tccb_listing.html", "https://www.tccb.gov.tr/en/news/"),
    ("iran_mfa", "iran_mfa_listing.html", "https://en.mfa.ir/portal/"),
    ("kantei", "kantei_listing.html", "https://japan.kantei.go.jp/105/"),
    ("president_lv", "president_lv_listing.html", "https://www.president.lv/en/article/"),
])
def test_listing_parsers_find_items(feed_id, fixture, prefix) -> None:
    es = _entries(feed_id, fixture)
    assert es and all(e.url.startswith(prefix) and e.title for e in es)


def test_listing_dates_before_after_and_in_url() -> None:
    assert [e.published for e in _entries("tccb", "tccb_listing.html")][:1] == ["2026-10-03"]      # date sits before the link
    assert any(e.published == "2026-10-03" for e in _entries("iran_mfa", "iran_mfa_listing.html"))  # ... after the link
    assert all(e.published.startswith("2026-") for e in _entries("kantei", "kantei_listing.html"))  # ... in the url


def test_url_dates_for_kantei_both_filename_styles() -> None:
    assert collect._url_date("https://japan.kantei.go.jp/105/statement/202610/1003shiji.html") == "2026-10-03"
    assert collect._url_date("https://japan.kantei.go.jp/105/actions/202609/29mongolia.html") == "2026-09-29"


def test_text_dates() -> None:
    assert collect._text_date("03.10.2026") == "2026-10-03"
    assert collect._text_date("Monday 5 October 2026") == "2026-10-05"
    assert collect._text_date("nothing here") == ""


def test_imageless_link_is_titled_from_its_slug() -> None:
    html = b'<a href="/en/article/president-meets-allies"><img src="x.png"></a>'
    [e] = collect.parse_listing(html, by_id("president_lv"))
    assert e.title == "President meets allies"
