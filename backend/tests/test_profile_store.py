"""The profile store never loses research — history, collision guard, kept reads."""

from __future__ import annotations

from pathlib import Path

from algent_backend.agent_system.agents.research.profile import SignalProfile
from algent_backend.agent_system.agents.research.store import JsonProfileStore


def _p(pid: str, title: str, rev: int = 1, url: str = "") -> SignalProfile:
    ledger = [{"id": "src_1", "url": url}] if url else []
    return SignalProfile.model_validate(
        {"id": pid, "title": title, "revision": rev, "source_ledger": ledger})


def test_a_different_story_never_takes_an_existing_slot(tmp_path: Path) -> None:
    # Live: "Megaprojects" and "Greenland" were both prof_unknown, and the second erased the first.
    store = JsonProfileStore(tmp_path)
    store.save(_p("prof_unknown", "Megaprojects"))
    store.save(_p("prof_unknown", "Greenland deal"))

    assert store.get("prof_unknown").title == "Megaprojects"      # the first story survives
    ids = store.list_ids()
    assert len(ids) == 2 and any(i.startswith("prof_unknown__") for i in ids)
    assert "Greenland deal" in (tmp_path / "_collisions.jsonl").read_text(encoding="utf-8")


def test_a_new_revision_of_the_same_story_updates_it_and_keeps_every_version(tmp_path: Path) -> None:
    store = JsonProfileStore(tmp_path)
    store.save(_p("prof_42", "Djibouti", rev=1))
    store.save(_p("prof_42", "Djibouti", rev=3))
    assert store.get("prof_42").revision == 3
    assert len(store.history("prof_42")) == 2                      # nothing overwritten, ever


def test_the_pages_read_are_kept_with_the_profile(tmp_path: Path) -> None:
    # This silently did nothing once: the method sat on the Protocol, not the store, and the
    # caller swallows errors — so a real store must be exercised, not just the call site.
    reads = tmp_path / "read_cache.jsonl"
    reads.write_text('{"url": "https://x"}\n', encoding="utf-8")
    store = JsonProfileStore(tmp_path / "store")
    assert store.save_reads("prof_42", reads)
    assert (tmp_path / "store" / "prof_42.reads.jsonl").read_text(encoding="utf-8").startswith("{")


def test_the_corpus_view_counts_links_between_stories(tmp_path: Path) -> None:
    from algent_backend.cli.newsroom.corpus import summarize

    store = JsonProfileStore(tmp_path)
    store.save(_p("prof_a", "Hormuz shipping", url="https://shared.example/x"))
    store.save(_p("prof_b", "Iran strikes", url="https://shared.example/x"))
    store.save(_p("prof_c", "Butterflies", url="https://other.example/y"))
    r = summarize(store)
    assert r["profiles"] == 3 and r["distinct_sources"] == 2
    assert r["sources_shared_by_2plus_stories"] == 1
    assert r["most_linked_story_pairs"][0]["shared"] == 1
