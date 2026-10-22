"""The site reads published files only and agrees with the writer on keys, shard counts and failure behaviour. TS is read as text (no node here)."""

from __future__ import annotations

import re
from pathlib import Path

from algent_backend.live import flags as live_flags
from algent_backend.publishing import doc_store, object_docs

SITE = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster"


def _ts(*parts: str) -> str:
    return SITE.joinpath(*parts).read_text(encoding="utf-8")


def test_no_site_source_reads_supabase() -> None:
    offenders = [str(p.relative_to(SITE)) for ext in ("*.ts", "*.tsx") for folder in ("lib", "app", "components") for p in (SITE / folder).rglob(ext)
                 if re.search(r"supabase|rest/v1|PostgREST", p.read_text(encoding="utf-8"), re.I) and "// legacy" not in p.read_text(encoding="utf-8")]
    assert offenders == [], offenders
    assert "NEXT_PUBLIC_DATA_BASE" in _ts("lib", "data-base.ts")


def test_the_reader_and_writer_agree_on_keys() -> None:
    ts = _ts("lib", "store.ts")
    assert "`${DATA_BASE}/docs/${rel}.gz`" in ts and doc_store.object_key("a/b.json") == "docs/a/b.json.gz"
    assert "`_names/${dir}.json`" in ts and object_docs.names_path("daily/ai") == "_names/daily/ai.json"
    assert '"articles/index.json"' in ts and "`articles/${slug}.json`" in ts


def test_a_bucket_failure_throws_instead_of_caching_an_empty_page() -> None:
    ts = _ts("lib", "store.ts")
    assert "res.status === 404) return null" in ts                       # not published: nothing
    assert "if (!res.ok) throw new DataUnavailable" in ts                # anything else: keep the last good page
    assert "phase-production-build" in ts                                # ...except at build time, when there is no page to keep
    for name in ("live.ts", "satellite.ts"):
        assert "throw new Error" in _ts("lib", name)


def test_trail_shards_and_polling_match_the_r2_profile() -> None:
    trails = _ts("components", "live", "trails.ts")
    assert f"SHIP_SHARDS = {live_flags.R2_TRACK_SHARDS};" in trails and f"AIR_SHARDS = {live_flags.R2_TRACK_SHARDS};" in trails
    assert f"POLL_MS = {live_flags.R2_SNAPSHOT_SECONDS}_000" in _ts("components", "live", "useLiveEntities.ts")


def test_every_page_has_a_per_product_revalidate_not_one_global_number() -> None:
    values = {}
    for p in (SITE / "app").rglob("*"):
        if p.is_file() and p.suffix in (".ts", ".tsx"):
            m = re.search(r"^export const revalidate = (\d+);", p.read_text(encoding="utf-8"), re.M)
            if m and "api" not in p.parts:
                values[str(p.relative_to(SITE))] = int(m.group(1))
    assert len(set(values.values())) >= 4, values
    assert min(values.values()) >= 120 and values["app/live/page.tsx".replace("/", __import__("os").sep)] == 120
