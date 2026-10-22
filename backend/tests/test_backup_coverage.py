"""The nightly backup must cover every durable store the code writes to - the server is the system of record, so a store missing from
``data_backup.sync._sources()`` is one dead disk away from being lost. This test makes that impossible to forget silently."""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend.data_backup import sync

PKG = Path(sync.__file__).resolve().parents[1]

#: env name of a store root -> the name it has in the backup mirror.
BACKED_UP = {
    "ALGENT_PROFILE_STORE": "profile_store",
    "ALGENT_PULSE_STORE": "pulse_store",
    "ALGENT_INTEL_STORE": "intel_store",
    "ALGENT_INSTRUMENTS_STORE": "instruments_store",
    "ALGENT_AI_BENCHMARKS_STORE": "ai_benchmarks_store",
    "ALGENT_STATEMENTS_STORE": "statements_store",
    "ALGENT_ACTORS_STORE": "actors_store",
    "ALGENT_GEOLEDGER_STORE": "geoledger_store",
    "ALGENT_SANCTIONS_STORE": "sanctions_store",
    "ALGENT_CALENDAR_STORE": "calendar_store",
    "ALGENT_MARKETS_STORE": "markets_store",
    "ALGENT_MARITIME_STORE": "maritime_daily",            # only the daily summaries: the raw positions / event log are GB and bounded by retention
    "ALGENT_DRAFT_STORE": "draft_store",
    "ALGENT_TREATMENT_STORE": "treatment_store",
    "ALGENT_LEAD_STORE": "lead_store",
}
#: Stores deliberately NOT mirrored, each with the reason. Adding a store to the code without adding it to one of the two tables fails the test.
EXCLUDED = {
    "ALGENT_RUNS_DIR": "run logs: rolling retention by design, indexed in runs_index.jsonl",
    "ALGENT_LIVE_STORE": "live feeds, hour files (60 d) and baselines: re-collected from public feeds; baselines relearn in ~3 weeks (the one real loss)",
    "ALGENT_LIBRARY_STORE": "the crawl cache (library.db): re-crawled by the library timer",
    "ALGENT_RETRIEVAL_STORE": "embeddings derived from the profile store",
    "ALGENT_FETCH_CACHE_DIR": "a page-fetch cache, refilled on demand",
    "ALGENT_INGESTION_DIR": "scratch output of the ingestion CLI",
}
PUBLISHED = ("site_articles", "site_intel", "site_radar", "site_data")      # what was published exists nowhere else once the database is gone


def _store_envs() -> set[str]:
    found: set[str] = set()
    for path in PKG.rglob("*.py"):
        if "tests" in path.parts:
            continue
        found |= set(re.findall(r"""["'](ALGENT_[A-Z_]*(?:STORE|_DIR))["']""", path.read_text(encoding="utf-8", errors="replace")))
    return found


def test_every_store_the_code_writes_is_backed_up_or_explicitly_excluded() -> None:
    envs = _store_envs()
    unknown = envs - set(BACKED_UP) - set(EXCLUDED)
    assert not unknown, f"new store(s) {sorted(unknown)}: add to data_backup.sync._sources() and BACKED_UP, or to EXCLUDED with a reason"
    assert all(len(reason) > 20 for reason in EXCLUDED.values())
    assert set(BACKED_UP) <= envs, "BACKED_UP names a store the code no longer has"


def test_each_backed_up_store_follows_the_same_location_the_code_writes_to(monkeypatch, tmp_path) -> None:
    for env, name in BACKED_UP.items():
        monkeypatch.setenv(env, str(tmp_path / env))
    sources = sync._sources()
    for env, name in BACKED_UP.items():
        assert name in sources, f"{name} missing from the backup"
        assert str(sources[name]).startswith(str(tmp_path / env)), f"{name} does not follow {env}"


def test_what_was_published_and_the_corpus_stores_are_mirrored() -> None:
    sources = sync._sources()
    assert set(PUBLISHED) <= set(sources)
    assert {"pulse_store", "geoledger_store", "sanctions_store", "calendar_store", "markets_store", "maritime_daily"} <= set(sources)


def test_the_mirror_copies_new_and_changed_files_and_never_deletes(tmp_path) -> None:
    src, dest = tmp_path / "pulse", tmp_path / "mirror"
    (src / "log").mkdir(parents=True)
    (src / "log" / "a.jsonl").write_text("1\n", encoding="utf-8")
    assert sync.mirror({"pulse_store": src}, dest) == 1
    assert sync.mirror({"pulse_store": src}, dest) == 0
    (src / "log" / "a.jsonl").write_text("1\n2\n", encoding="utf-8")
    (src / "log" / "a.jsonl.tmp").write_text("partial", encoding="utf-8")
    assert sync.mirror({"pulse_store": src}, dest) == 1
    (src / "log" / "a.jsonl").unlink()
    sync.mirror({"pulse_store": src}, dest)
    assert (dest / "pulse_store" / "log" / "a.jsonl").read_text(encoding="utf-8") == "1\n2\n"          # an accident must not propagate
