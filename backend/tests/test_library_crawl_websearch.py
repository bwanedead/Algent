"""Library crawl (offline, injected network) and the web_search integration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from algent_backend.agent_system.tools.sourcing.search import circuit, research
from algent_backend.library import crawl as crawlmod
from algent_backend.library import net as netmod
from algent_backend.library import sources, store
from algent_backend.library.search import search

FIX = Path(__file__).parent / "fixtures" / "library"
NOW = datetime(2026, 10, 4, 21, 0, tzinfo=UTC)
FEED = "https://news.un.org/feed/subscribe/en/news/all/rss.xml"
SITEMAP = "https://kyivindependent.com/news-sitemap.xml"
BODY = "Peacekeepers reported ceasefire violations near the border and aid convoys were delayed. " * 12


class FakeWorld:
    """Routes for feeds/robots, a page reader, and a call log."""

    def __init__(self) -> None:
        self.routes = {FEED: netmod.Response(200, (FIX / "un_news_feed.xml").read_bytes(), {"etag": '"e1"'}),
                       SITEMAP: netmod.Response(200, (FIX / "kyiv_news_sitemap.xml").read_bytes())}
        self.reads: list[str] = []
        self.get_log: list[tuple[str, dict]] = []
        self.fail_pages: set[str] = set()

    def http(self, url: str, headers: dict) -> netmod.Response:
        self.get_log.append((url, headers))
        if url in self.routes:
            r = self.routes[url]
            if headers.get("If-None-Match") and r.headers.get("etag") == headers["If-None-Match"]:
                return netmod.Response(304)
            return r
        return netmod.Response(404)

    def read(self, url: str) -> dict:
        self.reads.append(url)
        if url in self.fail_pages:
            raise RuntimeError("Could not extract content")
        return {"url": url, "content": f"{BODY} page {url}", "via": "trafilatura", "quality": "good", "meta": {"title": "Meta"}}

    def net(self) -> netmod.Net:
        return netmod.Net(http=self.http, read_page=self.read, sleep=lambda s: None, pace_s=0)


@pytest.fixture()
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIBRARY_STORE", str(tmp_path / "lib"))
    return FakeWorld()


def run(world: FakeWorld, ids=("un_news",), **kw):
    return crawlmod.crawl(list(ids), net=world.net(), now=NOW, **kw)


def test_crawl_indexes_new_pages_and_respects_per_source_cap(world) -> None:
    rep = run(world, per_source=4)
    assert rep["totals"]["new"] == 4 and len(world.reads) == 4
    assert rep["sources"]["un_news"]["pending"] >= 10
    conn = store.connect(create=False)
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE source_id='un_news' AND latest=1").fetchone()[0] == 4
    conn.close()
    assert search("ceasefire violations", now=NOW)


def test_second_crawl_is_idempotent_and_uses_etag(world) -> None:
    run(world, per_source=50)
    n_reads = len(world.reads)
    rep2 = run(world, per_source=50)
    assert len(world.reads) == n_reads                      # nothing refetched
    assert rep2["totals"]["feeds_not_modified"] == 1 and rep2["totals"]["new"] == 0
    # even with the validator gone, known urls with unchanged stamps are skipped
    conn = store.connect()
    store.save_feed_state(conn, FEED, "un_news", etag="", last_modified="")
    conn.close()
    rep3 = run(world, per_source=50)
    assert len(world.reads) == n_reads and rep3["totals"]["new"] == 0 and rep3["sources"]["un_news"]["pending"] == 0


def test_overall_cap_round_robins_across_sources(world) -> None:
    rep = run(world, ids=("un_news", "kyivindependent"), max_total=4, per_source=10)
    per = {sid: r.get("new", 0) for sid, r in rep["sources"].items()}
    assert sum(per.values()) == 4 and per["un_news"] == 2 and per["kyivindependent"] == 2


def test_sitemap_candidates_carry_title_without_a_page_title(world) -> None:
    run(world, ids=("kyivindependent",), per_source=2)
    conn = store.connect(create=False)
    titles = [r[0] for r in conn.execute("SELECT title FROM documents WHERE source_id='kyivindependent'")]
    conn.close()
    assert titles and all(t and t != "Meta" for t in titles)


def test_changed_stamp_with_new_text_makes_a_revision(world) -> None:
    run(world, per_source=50)
    conn = store.connect()
    url = conn.execute("SELECT url FROM documents WHERE source_id='un_news' LIMIT 1").fetchone()[0]
    conn.execute("UPDATE documents SET stamp='old-stamp' WHERE url=?", (url,))
    conn.commit()
    store.save_feed_state(conn, FEED, "un_news", etag="")
    conn.close()
    world.read = lambda u: {"url": u, "content": "Entirely rewritten report about the delegation. " * 20, "via": "trafilatura", "quality": "good"}
    rep = crawlmod.crawl(["un_news"], net=netmod.Net(http=world.http, read_page=world.read, sleep=lambda s: None, pace_s=0), now=NOW, per_source=50)
    assert rep["totals"]["revised"] == 1
    conn = store.connect(create=False)
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE url=?", (url,)).fetchone()[0] == 2
    conn.close()


def test_failed_pages_are_recorded_then_parked(world, monkeypatch) -> None:
    monkeypatch.setattr(crawlmod, "MIN_SUMMARY_WORDS", 10_000)               # no blurb fallback: the failure must register
    run(world, per_source=1)
    conn = store.connect(create=False)
    first = conn.execute("SELECT url FROM documents WHERE source_id='un_news'").fetchone()[0]
    conn.close()
    bad = next(c.url for c in crawlmod.parse_feed(world.routes[FEED].body) if c.url != first)
    world.fail_pages.add(bad)
    for _ in range(crawlmod.PAGE_PARK_AFTER + 1):
        c = store.connect()
        store.save_feed_state(c, FEED, "un_news", etag="")          # a changed feed: the failed url is listed again
        c.close()
        run(world, per_source=50, max_total=1000)
    conn = store.connect(create=False)
    row = conn.execute("SELECT failures, parked FROM page_failures WHERE url=?", (bad,)).fetchone()
    conn.close()
    assert row["parked"] == 1 and row["failures"] == crawlmod.PAGE_PARK_AFTER
    assert world.reads.count(bad) == crawlmod.PAGE_PARK_AFTER                    # never read again once parked


def test_failed_page_falls_back_to_the_feed_summary(world) -> None:
    from algent_backend.library.parse import Candidate

    world.fail_pages.add("https://x.test/p")
    conn = store.connect()
    src = sources.by_id("un_news")
    cand = Candidate("https://x.test/p", "Title", NOW.isoformat(), "s", "A feed blurb that is long enough to be a real summary of what happened today.")
    assert crawlmod._index(conn, world.net(), src, cand, NOW)[0] == "new"
    assert conn.execute("SELECT via FROM documents WHERE url='https://x.test/p'").fetchone()[0] == "feed_summary"
    conn.close()


def test_robots_refusal_skips_the_page_and_parks_it(world) -> None:
    world.routes["https://news.un.org/robots.txt"] = netmod.Response(200, b"User-agent: *\nDisallow: /feed/view/\n")
    rep = run(world)
    assert rep["totals"]["robots"] > 0 and rep["totals"]["new"] == 0 and world.reads == []


def test_feed_failures_park_the_feed(world) -> None:
    world.routes[FEED] = netmod.Response(503)
    for _ in range(crawlmod.FEED_PARK_AFTER):
        rep = run(world)
        assert rep["totals"]["feeds_failed"] == 1
    assert run(world)["totals"]["feeds_parked"] == 1
    conn = store.connect(create=False)
    assert store.feed_state(conn, FEED)["failures"] == crawlmod.FEED_PARK_AFTER
    conn.close()


def test_stats_reports_documents_and_failures(world) -> None:
    run(world, per_source=3)
    conn = store.connect(create=False)
    s = store.stats(conn)
    conn.close()
    assert s["documents"] == 3 and s["sources"][0]["source_id"] == "un_news" and s["db_bytes"] > 0


# -- web_search integration ------------------------------------------------------------------------
@pytest.fixture()
def lib_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIBRARY_STORE", str(tmp_path / "wslib"))
    circuit.reset()
    c = store.connect()
    store.add_document(c, store.Doc(url="https://www.federalreserve.gov/x", source_id="fed", domain="www.federalreserve.gov",
                                    kind="central_bank", title="Fed holds rates", text="The Federal Reserve held interest rates steady.",
                                    fetched_at=datetime.now(UTC).isoformat(), published=datetime.now(UTC).isoformat()))
    c.close()
    yield
    circuit.reset()


def _external(monkeypatch, results=None, fail=False):
    def fake(provider, query, max_results):
        if fail:
            raise RuntimeError("down")
        return results if results is not None else [{"title": "Web hit", "url": "https://w.test/1", "content": "snippet"}]

    monkeypatch.setattr(research, "_invoke_provider", fake)


def test_web_search_puts_library_hits_first_and_keeps_the_engine(lib_store, monkeypatch) -> None:
    _external(monkeypatch)
    out = research._search_web("federal reserve rates", "keyword", 5)
    assert out["provider"] == "ddg" and out["library_hits"] == 1
    assert out["results"][0]["provider"] == "library" and out["results"][0]["source_kind"] == "central_bank"
    assert out["results"][1]["url"] == "https://w.test/1"
    assert "OUR OWN INDEX" in out["library_style"] and out["provider_style"]


def test_web_search_unchanged_when_library_has_nothing(lib_store, monkeypatch) -> None:
    _external(monkeypatch)
    out = research._search_web("zzzunmatchable", "keyword", 5)
    assert out["results"] == [{"title": "Web hit", "url": "https://w.test/1", "content": "snippet"}]
    assert "library_hits" not in out and "library_style" not in out


def test_web_search_unchanged_without_a_library_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_LIBRARY_STORE", str(tmp_path / "absent"))
    circuit.reset()
    _external(monkeypatch)
    out = research._search_web("federal reserve", "keyword", 5)
    assert "library_hits" not in out and not (tmp_path / "absent").exists()


def test_web_search_semantic_does_not_consult_the_library(lib_store, monkeypatch) -> None:
    _external(monkeypatch)
    out = research._search_web("federal reserve rates", "semantic", 5)
    assert "library_hits" not in out


def test_web_search_news_kind_uses_the_library(lib_store, monkeypatch) -> None:
    _external(monkeypatch)
    assert research._search_web("federal reserve", "news", 5)["library_hits"] == 1


def test_library_answers_alone_when_every_engine_fails(lib_store, monkeypatch) -> None:
    _external(monkeypatch, fail=True)
    out = research._search_web("federal reserve", "keyword", 5)
    assert out["provider"] == "library" and out["results"][0]["url"].startswith("https://www.federalreserve.gov") \
        and "external_search_unavailable" in out and "error" not in out


def test_a_broken_library_never_breaks_web_search(lib_store, monkeypatch) -> None:
    import algent_backend.library.search as libsearch

    monkeypatch.setattr(libsearch, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("corrupt db")))
    _external(monkeypatch)
    out = research._search_web("federal reserve", "keyword", 5)
    assert out["results"][0]["url"] == "https://w.test/1"
