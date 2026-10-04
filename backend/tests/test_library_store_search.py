"""Library store (revisions, FTS), ranking, and retention. Offline, temp store."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from algent_backend.library import store
from algent_backend.library.search import search

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_LIBRARY_STORE", str(tmp_path / "lib"))
    c = store.connect()
    yield c
    c.close()


def doc(url: str, text: str, *, kind: str = "wire", source: str = "s", title: str = "", age_days: float = 1,
        stamp: str = "") -> store.Doc:
    published = (NOW - timedelta(days=age_days)).isoformat()
    return store.Doc(url=url, source_id=source, domain=url.split("/")[2], kind=kind, title=title or url, text=text,
                     fetched_at=NOW.isoformat(timespec="seconds"), published=published, stamp=stamp, region="x")


def test_new_unchanged_revised_lifecycle(conn) -> None:
    assert store.add_document(conn, doc("https://a.test/1", "Kaliningrad air defence drills", stamp="v1")) == "new"
    assert store.add_document(conn, doc("https://a.test/1", "Kaliningrad air defence drills", stamp="v2")) == "unchanged"
    assert store.known_stamp(conn, "https://a.test/1") == "v2"                  # only the stamp moved
    assert store.add_document(conn, doc("https://a.test/1", "Kaliningrad drills cancelled after talks", stamp="v3")) == "revised"
    rows = conn.execute("SELECT revision, latest FROM documents WHERE url='https://a.test/1' ORDER BY revision").fetchall()
    assert [(r[0], r[1]) for r in rows] == [(1, 0), (2, 1)]                     # old revision kept, not latest


def test_search_sees_only_the_latest_revision(conn) -> None:
    store.add_document(conn, doc("https://a.test/1", "alpha bravo original wording"))
    store.add_document(conn, doc("https://a.test/1", "alpha bravo corrected wording"))
    assert [h["url"] for h in search("original", now=NOW)] == []
    assert [h["url"] for h in search("corrected", now=NOW)] == ["https://a.test/1"]


def test_search_hit_shape_and_snippet(conn) -> None:
    store.add_document(conn, doc("https://a.test/1", "Ships crossing the Strait of Hormuz fell sharply this week " * 3,
                                 title="Hormuz traffic", source="un_news", kind="international_org"))
    (hit,) = search("Strait of Hormuz shipping", now=NOW)                         # AND fails ("shipping"), OR fallback finds it
    assert {"title", "url", "source", "kind", "published", "snippet"} <= set(hit)
    assert hit["source"] == "un_news" and "Hormuz" in hit["snippet"]


def test_primary_beats_news_on_equal_relevance(conn) -> None:
    body = "sanctions package Ethiopia Eritrea border talks"
    store.add_document(conn, doc("https://news.test/a", body, kind="wire", title="Ethiopia Eritrea talks"))
    store.add_document(conn, doc("https://gov.test/a", body, kind="government", title="Ethiopia Eritrea talks"))
    store.add_document(conn, doc("https://tank.test/a", body, kind="think_tank", title="Ethiopia Eritrea talks"))
    assert [h["url"] for h in search("Ethiopia Eritrea", now=NOW)] == [
        "https://gov.test/a", "https://tank.test/a", "https://news.test/a"]


def test_recency_orders_equal_matches_but_never_drops_old_ones(conn) -> None:
    body = "grain corridor Black Sea"
    store.add_document(conn, doc("https://a.test/old", body, age_days=200, title="grain corridor"))
    store.add_document(conn, doc("https://a.test/new", body, age_days=1, title="grain corridor"))
    store.add_document(conn, doc("https://a.test/mid", body, age_days=30, title="grain corridor"))
    assert [h["url"] for h in search("grain corridor", now=NOW)] == [
        "https://a.test/new", "https://a.test/mid", "https://a.test/old"]


def test_relevance_can_beat_recency_and_kind(conn) -> None:
    store.add_document(conn, doc("https://gov.test/vague", "a long statement " + "filler " * 150 + " mentions Kaliningrad once",
                                 kind="government", title="Weekly bulletin", age_days=1))
    store.add_document(conn, doc("https://news.test/exact", "Kaliningrad Kaliningrad blockade Kaliningrad",
                                 kind="wire", title="Kaliningrad blockade", age_days=20))
    assert search("Kaliningrad", now=NOW)[0]["url"] == "https://news.test/exact"


def test_filters_days_kinds_site_and_phrase(conn) -> None:
    store.add_document(conn, doc("https://www.bbc.com/a", "Hormuz tanker traffic", kind="wire", age_days=2))
    store.add_document(conn, doc("https://imf.test/b", "Hormuz tanker traffic", kind="international_org", age_days=40))
    assert {h["url"] for h in search("Hormuz", days=7, now=NOW)} == {"https://www.bbc.com/a"}
    assert {h["url"] for h in search("Hormuz", kinds=["international_org"], now=NOW)} == {"https://imf.test/b"}
    assert {h["url"] for h in search("site:bbc.com Hormuz", now=NOW)} == {"https://www.bbc.com/a"}
    assert search('"tanker traffic"', now=NOW) and not search('"traffic tanker"', now=NOW)


def test_search_on_absent_store_returns_nothing_and_creates_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALGENT_LIBRARY_STORE", str(tmp_path / "nothing"))
    assert search("anything") == []
    assert not (tmp_path / "nothing").exists()


def test_punctuation_and_fts_syntax_in_queries_are_harmless(conn) -> None:
    store.add_document(conn, doc("https://a.test/1", "NATO summit; Russia (and) Belarus - AND OR NOT"))
    assert search('NATO: "summit" -- (Russia) OR* NEAR/3', now=NOW)
    assert search("   ", now=NOW) == []


# -- retention ---------------------------------------------------------------------------------------
def test_retention_by_age_tier_and_old_revisions(conn) -> None:
    store.add_document(conn, doc("https://n.test/old", "stale news item", kind="wire", age_days=120))
    store.add_document(conn, doc("https://n.test/ok", "recent news item", kind="wire", age_days=10))
    store.add_document(conn, doc("https://g.test/old", "old government record", kind="government", age_days=400))
    store.add_document(conn, doc("https://r.test/1", "report first draft", kind="wire", age_days=1))
    store.add_document(conn, doc("https://r.test/1", "report second draft", kind="wire", age_days=1))
    later = NOW + timedelta(days=store.REVISION_KEEP_DAYS + 1)
    removed = store.enforce_retention(conn, now=later)
    assert removed["old_revisions"] == 1
    urls = {r[0] for r in conn.execute("SELECT url FROM documents")}
    assert "https://n.test/old" not in urls and "https://n.test/ok" in urls     # news: 90-day limit
    assert "https://g.test/old" in urls                                         # primary: 730-day limit
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE url='https://r.test/1'").fetchone()[0] == 1
    assert search("stale", now=NOW) == [] and search("government record", now=NOW)   # index followed the deletes


def test_retention_over_budget_drops_news_before_primary(conn) -> None:
    for i in range(40):
        store.add_document(conn, doc(f"https://n.test/{i}", f"news body number {i} " + "word " * 400, kind="wire", age_days=i % 5))
    store.add_document(conn, doc("https://g.test/keep", "government body " + "word " * 400, kind="government", age_days=3))
    removed = store.enforce_retention(conn, now=NOW, max_bytes=60_000)
    assert removed["over_budget"] > 0
    assert store.live_bytes(conn) <= 60_000
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE url='https://g.test/keep'").fetchone()[0] == 1
