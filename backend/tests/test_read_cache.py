"""A page is fetched once per article, however many stages or lanes ask for it.

Measured live: one gauntlet made 59 page reads covering 27 distinct pages — the IUCN page six
times, one journal attachment five times — and 24 paid-crawler reads covering 13 pages. Page
reads are the scarcest resource this newsroom has.
"""

from __future__ import annotations

import pytest

from algent_backend.agent_system.foundation import read_cache, snapshots
from algent_backend.agent_system.tools.sourcing.search import policy, research

GOOD = {"url": "https://example.test/a", "content": "the full page " * 50, "quality": "good"}
THIN = {"url": "https://example.test/wall", "content": "Just a moment...", "quality": "thin"}


@pytest.fixture
def fetches(monkeypatch):
    """Count real fetches; answer from a fixed table."""
    calls: list[tuple[str, bool]] = []
    table = {"https://example.test/a": GOOD, "https://example.test/wall": THIN}

    def fake_fetch(url, allow_paid_fallback=False):
        calls.append((url, allow_paid_fallback))
        return dict(table[url])

    monkeypatch.setattr("algent_backend.agent_system.tools.sourcing.depth.fetch_content._fetch",
                        fake_fetch)
    monkeypatch.setattr(policy, "is_allowed", lambda channel: True)
    monkeypatch.setattr(research, "_can_afford_paid", lambda channel: None)
    return calls


def test_the_same_page_is_fetched_once_across_repeated_asks(fetches) -> None:
    with read_cache.scoped():
        first = research._search_read("https://example.test/a", richness="standard")
        again = research._search_read("https://example.test/a/", richness="standard")  # same page
        third = research._search_read("https://example.test/a#section", richness="standard")
    assert len(fetches) == 1
    assert not first.get("cached") and again["cached"] and third["cached"]
    assert again["content"] == first["content"]


def test_a_thin_read_is_not_cached_so_the_paid_retry_still_happens(fetches) -> None:
    """A wall is exactly when the paid crawler earns its cost; caching it would block that."""
    with read_cache.scoped():
        research._search_read("https://example.test/wall", richness="standard")
        research._search_read("https://example.test/wall", richness="rich")
    assert len(fetches) == 2
    assert fetches[1] == ("https://example.test/wall", True)


def test_a_good_free_read_makes_a_later_paid_read_of_the_page_free(fetches) -> None:
    """A rich read of a page already held in full is pure waste of the scarcest credit."""
    reserved: list[str] = []
    with read_cache.scoped():
        research._search_read("https://example.test/a", richness="standard")
        import algent_backend.agent_system.foundation.cost as cost_mod

        original = cost_mod.try_reserve

        def spy(*a, **k):
            reserved.append(k.get("op", ""))
            return original(*a, **k)

        cost_mod.try_reserve = spy
        try:
            out = research._search_read("https://example.test/a", richness="rich")
        finally:
            cost_mod.try_reserve = original
    assert out["cached"] and len(fetches) == 1 and reserved == []


def test_a_cache_hit_still_counts_as_a_read_for_grounding(fetches) -> None:
    """Each lane starts with an empty snapshot store; a page served from cache was still read."""
    with read_cache.scoped():
        research._search_read("https://example.test/a", richness="standard")
        with snapshots.scoped():                       # a later lane's fresh store
            research._search_read("https://example.test/a", richness="standard")
            assert "https://example.test/a" in snapshots.collected()


def test_lane_scopes_do_not_reset_the_run_cache(fetches) -> None:
    """The bug being fixed: per-lane scopes wiped memory between lanes."""
    with read_cache.scoped():
        research._search_read("https://example.test/a", richness="standard")
        with read_cache.scoped():                      # a nested lane asking for its own scope
            out = research._search_read("https://example.test/a", richness="standard")
    assert out["cached"] and len(fetches) == 1


def test_reads_persist_so_resume_does_not_rebuy_them(fetches, tmp_path) -> None:
    path = tmp_path / "read_cache.jsonl"
    with read_cache.scoped(path):
        research._search_read("https://example.test/a", richness="standard")
    with read_cache.scoped(path):                      # a resumed run, new process
        out = research._search_read("https://example.test/a", richness="standard")
    assert out["cached"] and len(fetches) == 1


def test_no_scope_means_no_behaviour_change(fetches) -> None:
    research._search_read("https://example.test/a", richness="standard")
    research._search_read("https://example.test/a", richness="standard")
    assert len(fetches) == 2


def test_a_blank_query_spends_nothing(monkeypatch) -> None:
    """One live gauntlet sent the same empty query seven times."""
    monkeypatch.setattr(policy, "is_allowed", lambda channel: True)
    sent: list[str] = []
    monkeypatch.setattr(research, "_search_web", lambda q, k, n: sent.append(q) or {})
    out = research._search(query="   ", kind="keyword")
    assert "error" in out and sent == []


def test_an_identical_search_is_answered_from_the_run(monkeypatch) -> None:
    monkeypatch.setattr(policy, "is_allowed", lambda channel: True)
    sent: list[str] = []

    def web(q, k, n):
        sent.append(q)
        return {"action": "search", "results": [{"url": "https://x.test"}]}

    monkeypatch.setattr(research, "_search_web", web)
    with read_cache.scoped():
        research._search(query="Leopardus tilcayo", kind="keyword")
        out = research._search(query="  leopardus   TILCAYO ", kind="keyword")
    assert sent == ["Leopardus tilcayo"] and out["cached"]
