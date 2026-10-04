"""Statements collection — offline: real captured feeds, mocked HTTP, no model."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from algent_backend.agent_system.agents.statements import collect, store
from algent_backend.agent_system.agents.statements.sources import SOURCES, by_id

FIX = Path(__file__).parent / "fixtures" / "statements"
NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def _http(routes: dict[str, str | Exception]):
    def get(url: str) -> bytes:
        hit = routes[url]
        if isinstance(hit, Exception):
            raise hit
        return (FIX / hit).read_bytes()
    return get


def _pages(texts: dict[str, str] | None = None, fail: set[str] | None = None):
    calls: list[str] = []

    def read(url: str) -> str:
        calls.append(url)
        if fail and url in fail:
            raise RuntimeError("page read was blocked")
        return (texts or {}).get(url, "A short but real statement about relations between states. " * 5)
    read.calls = calls                                  # type: ignore[attr-defined]
    return read


def _run(feed_id: str, route: str, tmp_path, **kw):
    src = by_id(feed_id)
    return collect.collect_source(src, root=tmp_path, now=NOW, sleep=lambda _s: None,
                                  http_get=kw.pop("http_get", _http({src.url: route})), **kw)


def test_kremlin_full_text_comes_from_the_feed_and_reruns_are_idempotent(tmp_path) -> None:
    pages = _pages()
    first = _run("kremlin_transcripts", "kremlin_transcripts.xml", tmp_path, read_page=pages)
    assert (first["entries"], first["collected"], first["failed"]) == (2, 2, 0)
    assert pages.calls == []                            # the feed already carried the text
    ts = [store.load_transcript(t, tmp_path) for t in store.transcript_ids(tmp_path)]
    assert all(t and t.feed == "kremlin_transcripts" and len(t.text) > 500 and t.published.startswith("2026-") for t in ts)
    assert all("</p>" not in t.text and "<div" not in t.text for t in ts)           # HTML flattened to paragraphs
    again = _run("kremlin_transcripts", "kremlin_transcripts.xml", tmp_path, read_page=pages)
    assert (again["new"], again["collected"]) == (0, 0)
    assert len(store.transcript_ids(tmp_path)) == 2


def test_whitehouse_and_state_carry_full_text(tmp_path) -> None:
    wh = _run("whitehouse", "whitehouse_news.xml", tmp_path, read_page=_pages())
    st = _run("state_dept", "state_press.xml", tmp_path, read_page=_pages())
    assert wh["collected"] == 3 and st["collected"] == 3 and not wh["errors"] and not st["errors"]


def test_page_sources_read_the_page_and_skip_non_statements(tmp_path) -> None:
    pages = _pages()
    report = _run("fcdo", "fcdo.atom", tmp_path, read_page=pages)
    assert report["entries"] == 3 and report["skipped"] == 2 and report["collected"] == 1   # two travel-advice items
    assert pages.calls == ["https://www.gov.uk/government/speeches/un-human-rights-council-63-uk-statement-for-the-interactive-dialogue-with-the-high-commissioner-on-the-oral-update-on-ukraine"]


def test_stale_items_are_outside_the_window(tmp_path) -> None:
    report = _run("kremlin_transcripts", "kremlin_transcripts.xml", tmp_path, read_page=_pages(),
                  days=1)                                # fixture items are 10-02 / 09-30; now is 10-04
    assert report["collected"] == 0 and report["skipped"] == 2


def test_listing_source_parses_links_and_dates(tmp_path) -> None:
    src = by_id("china_mfa")
    entries = collect.parse_listing((FIX / "china_mfa_listing.html").read_bytes(), src)
    assert len(entries) >= 3 and all(e.url.startswith("https://www.mfa.gov.cn/eng/xw/fyrbt/") for e in entries)
    assert all(len(e.published) == 10 and e.title for e in entries)
    pages = _pages()
    report = _run("china_mfa", "china_mfa_listing.html", tmp_path, read_page=pages, max_new=2)
    assert report["collected"] == 2 and report["new"] >= 3 and len(pages.calls) == 2   # capped per run


def test_ec_api_route_returns_the_statement_body(tmp_path) -> None:
    ec = by_id("ec_presscorner")
    api = "https://ec.europa.eu/commission/presscorner/api/documents?language=en&reference=STATEMENT/26/2063"
    report = _run("ec_presscorner", "ec_presscorner.xml", tmp_path, read_page=_pages(),
                  http_get=_http({ec.url: "ec_presscorner.xml", api: "ec_statement_26_2063.json"}))
    assert report["collected"] == 1
    t = store.load_transcript(store.transcript_ids(tmp_path)[0], tmp_path)
    assert "Civilians are trapped under siege" in t.text and "<p>" not in t.text


def test_the_same_event_from_a_second_feed_is_not_collected_twice(tmp_path) -> None:
    _run("kremlin_transcripts", "kremlin_transcripts.xml", tmp_path, read_page=_pages())
    mirrored = (FIX / "kremlin_transcripts.xml").read_bytes().replace(b"/transcripts/8", b"/news/8")   # new urls, same events
    news = _run("kremlin_news", "", tmp_path, read_page=_pages(), http_get=lambda _u: mirrored)
    assert news["collected"] == 0 and news["skipped"] == 2 and len(store.transcript_ids(tmp_path)) == 2


def test_a_dead_feed_and_a_bad_page_never_abort_the_run(tmp_path) -> None:
    routes = {s.url: "fcdo.atom" for s in SOURCES}
    routes[by_id("whitehouse").url] = RuntimeError("ConnectError: down")
    reports = collect.collect(feeds=["whitehouse", "fcdo"], root=tmp_path, now=NOW, sleep=lambda _s: None,
                              http_get=_http(routes), read_page=_pages(fail={"x"}))
    by_feed = {r["feed"]: r for r in reports}
    assert by_feed["whitehouse"]["errors"] and by_feed["whitehouse"]["collected"] == 0
    assert by_feed["fcdo"]["collected"] == 1


def test_failing_urls_are_retried_then_parked(tmp_path) -> None:
    url = collect.parse_feed((FIX / "fcdo.atom").read_bytes())[0].url
    for attempt in range(collect.MAX_ATTEMPTS + 2):
        pages = _pages(fail={url})
        report = _run("fcdo", "fcdo.atom", tmp_path, read_page=pages)
        assert (len(pages.calls) == 1) == (attempt < collect.MAX_ATTEMPTS)
    assert store.load_seen(tmp_path)["failed"][url] == collect.MAX_ATTEMPTS and report["failed"] == 0
