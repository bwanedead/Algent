"""
Offline tests for the data-ingestion pipeline (sources, digest, CLI surface).

No network: parsers run on synthetic batches, lenses/pillars/digest are pure
functions over hand-built records, and the CLI commands run against fake sources.
The live fetch paths (``*_fetch_smoke``) run only when explicitly enabled, so the
default suite stays hermetic.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import zipfile
from datetime import UTC, datetime

import pytest

from algent_backend.data_ingestion.cli import _shared
from algent_backend.data_ingestion.cli import digest as digest_cmd
from algent_backend.data_ingestion.cli import fetch as fetch_cmd
from algent_backend.data_ingestion.cli import insights as insights_cmd
from algent_backend.data_ingestion.cli import sample as sample_cmd
from algent_backend.data_ingestion.news_production.discovery import lenses, ranking, sampling
from algent_backend.data_ingestion.news_production.discovery.candidates import extract_candidates
from algent_backend.data_ingestion.news_production.discovery.digest import build_digest
from algent_backend.data_ingestion.news_production.discovery.insights import build_insights
from algent_backend.data_ingestion.news_production.discovery.memory import (
    RollingMemory,
    load_memory,
    save_memory,
)
from algent_backend.data_ingestion.news_production.discovery.pillars import pillar_for_theme
from algent_backend.data_ingestion.news_production.sources import gdelt_gkg, gdelt_ngrams
from algent_backend.data_ingestion.news_production.sources.packet import RawPacket, RawPart
from algent_backend.data_ingestion.news_production.sources.records import GkgRecord


def _rec(language="eng", themes=(), tone=None, persons=(), organizations=(), **kw) -> GkgRecord:
    return GkgRecord(
        record_id=kw.get("record_id", "r"),
        url=kw.get("url", "http://x"),
        source_name=kw.get("source_name", "x.com"),
        language=language,
        themes=tuple(themes),
        persons=tuple(persons),
        organizations=tuple(organizations),
        tone=tone,
    )


# -- GKG parsing --------------------------------------------------------------


def _gkg_row(fields: dict[int, str]) -> str:
    row = [""] * 27
    for idx, value in fields.items():
        row[idx] = value
    return "\t".join(row)


def test_parse_row_extracts_fields_and_defaults_language_to_english() -> None:
    row = _gkg_row(
        {
            0: "REC1",
            3: "bbc.com",
            4: "http://bbc.com/a",
            7: "ECON_STOCKMARKET;ENV_CLIMATE;",
            11: "jane doe",
            13: "united nations",
            15: "-3.5,4.0,7.5,11.5",
            25: "",  # empty translation => English source
        }
    )
    [record] = gdelt_gkg.parse_gkg(_zip_bytes(row))
    assert record.record_id == "REC1"
    assert record.url == "http://bbc.com/a"
    assert record.language == "eng"
    assert record.themes == ("ECON_STOCKMARKET", "ENV_CLIMATE")
    assert record.persons == ("jane doe",)
    assert record.organizations == ("united nations",)
    assert record.tone == -3.5


def test_parse_row_reads_source_language_from_translation_info() -> None:
    row = _gkg_row({0: "R", 4: "u", 25: "srclc:fra;eng:Moses;..."})
    [record] = gdelt_gkg.parse_gkg(_zip_bytes(row))
    assert record.language == "fra"


def test_parse_skips_malformed_rows() -> None:
    good = _gkg_row({0: "R", 4: "u"})
    assert len(gdelt_gkg.parse_gkg(_zip_bytes(good + "\n" + "too\tshort"))) == 1


def _zip_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("batch.gkg.csv", text)
    return buf.getvalue()


# -- pillars ------------------------------------------------------------------


def test_pillar_mapping_by_prefix() -> None:
    assert pillar_for_theme("ECON_STOCKMARKET") == "economy"
    assert pillar_for_theme("ENV_CLIMATE") == "environment"
    assert pillar_for_theme("ELECTION_FRAUD") == "politics"
    assert pillar_for_theme("WHATEVER_UNCODED") is None


# -- lenses -------------------------------------------------------------------


def test_volume_lens_ranks_by_frequency() -> None:
    records = [_rec(themes=["A", "B"]), _rec(themes=["A"]), _rec(themes=["A", "C"])]
    assert lenses.volume_lens(records, top=2) == [("A", 3), ("B", 1)] or lenses.volume_lens(
        records, top=2
    ) == [("A", 3), ("C", 1)]


def test_rarity_lens_surfaces_the_long_tail() -> None:
    records = [_rec(themes=["LOUD"]) for _ in range(5)] + [_rec(themes=["NICHE"])]
    rare = lenses.rarity_lens(records, max_count=2)
    assert ("NICHE", 1) in rare
    assert all(theme != "LOUD" for theme, _ in rare)


def test_tone_lens_splits_negative_and_positive_with_support() -> None:
    records = (
        [_rec(themes=["GLOOM"], tone=-8.0) for _ in range(3)]
        + [_rec(themes=["CHEER"], tone=6.0) for _ in range(3)]
        + [_rec(themes=["THIN"], tone=-50.0)]  # below min_support, excluded
    )
    negative, positive = lenses.tone_lens(records, min_support=3)
    assert negative[0][0] == "GLOOM"
    assert positive[0][0] == "CHEER"
    assert all(theme != "THIN" for theme, _, _ in negative + positive)


# -- digest -------------------------------------------------------------------


def test_build_digest_groups_by_language_axis() -> None:
    records = [
        _rec(language="eng", themes=["ECON_STOCKMARKET"], tone=1.0),
        _rec(language="eng", themes=["ECON_STOCKMARKET"], tone=1.0),
        _rec(language="fra", themes=["ENV_CLIMATE"], tone=-2.0),
    ]
    digest = build_digest(records, source="gdelt_gkg", batch_id="20260101000000")

    assert digest.total_records == 3
    assert [lang.language for lang in digest.languages] == ["eng", "fra"]  # largest first
    eng = digest.languages[0]
    assert eng.record_count == 2
    assert eng.pillar_volume == {"economy": 2}
    assert eng.top_themes[0].theme == "ECON_STOCKMARKET"
    assert eng.top_themes[0].pillar == "economy"


# -- NGrams source ------------------------------------------------------------


def test_ngrams_build_packet_counts_records() -> None:
    ndjson = '{"ngram": "a"}\n{"ngram": "b"}\n\n'  # blank line ignored
    gz = gzip.compress(ndjson.encode("utf-8"))
    packet = gdelt_ngrams._build_packet("20260101000100", gz)
    assert packet.source == "gdelt_ngrams"
    assert packet.batch_id == "20260101000100"
    assert len(packet.parts) == 1
    assert packet.parts[0].name == "webngrams.ndjson"
    assert packet.parts[0].record_count == 2


def test_ngrams_latest_packet_url_walks_back_to_first_hit() -> None:
    now = datetime(2026, 1, 1, 0, 10, 0, tzinfo=UTC)
    available = "20260101000700.webngrams.json.gz"  # 3 minutes back

    class _FakeClient:
        def head(self, url):
            return type("R", (), {"status_code": 200 if url.endswith(available) else 404})()

        def close(self):
            pass

    batch_id, url = gdelt_ngrams.latest_packet_url(client=_FakeClient(), now=now)
    assert batch_id == "20260101000700"
    assert url.endswith(available)


# -- CLI ----------------------------------------------------------------------


def test_fetch_cli_lands_raw_parts_and_prints_summary(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    packet = RawPacket(
        source="gdelt_gkg",
        batch_id="20260101000000",
        parts=(
            RawPart(name="english.gkg.csv", text="row1\nrow2\n", record_count=2),
            RawPart(name="translation.gkg.csv", text="row1\n", record_count=1),
        ),
    )
    monkeypatch.setattr(_shared.SOURCES["gdelt_gkg"], "fetch_latest_raw", lambda: packet)

    assert fetch_cmd.run(_ns(source="gdelt_gkg", keep=1)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["batch_id"] == "20260101000000"
    assert [p["name"] for p in out["parts"]] == ["english.gkg.csv", "translation.gkg.csv"]
    landed = os.path.join(out["raw_dir"], "english.gkg.csv")
    assert open(landed, encoding="utf-8").read() == "row1\nrow2\n"


def test_digest_cli_writes_digest_and_prints_summary(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    monkeypatch.setitem(
        digest_cmd._FETCHERS,
        "gdelt_gkg",
        lambda: ("20260101000000", [_rec(themes=["ECON_STOCKMARKET"], tone=1.0)]),
    )

    assert digest_cmd.run(_ns(source="gdelt_gkg", keep=1)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["batch_id"] == "20260101000000"
    assert out["total_records"] == 1
    assert os.path.exists(out["digest_path"])
    written = json.loads(open(out["digest_path"], encoding="utf-8").read())
    assert written["languages"][0]["language"] == "eng"


# -- retention (one-in-one-out) -----------------------------------------------


def _fake_packet(batch_id: str) -> RawPacket:
    return RawPacket(
        source="gdelt_gkg",
        batch_id=batch_id,
        parts=(RawPart(name="english.gkg.csv", text="row\n", record_count=1),),
    )


def test_fetch_keeps_only_newest_and_reports_purged(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))

    out = {}
    for batch in ("20260101000000", "20260101001500"):
        monkeypatch.setattr(
            _shared.SOURCES["gdelt_gkg"], "fetch_latest_raw", lambda b=batch: _fake_packet(b)
        )
        fetch_cmd.run(_ns(source="gdelt_gkg", keep=1))
        out = json.loads(capsys.readouterr().out)  # drain per fetch; keep the last summary

    remaining = sorted(p.name for p in (tmp_path / "raw" / "gdelt_gkg").iterdir())
    assert remaining == ["20260101001500"]  # only the newest batch survives
    assert out["purged"] == ["20260101000000"]


def test_prune_digest_files_keeps_newest_per_source(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    d = _shared.digests_dir()
    d.mkdir(parents=True)
    for name in ("gdelt_gkg_20260101000000.json", "gdelt_gkg_20260101001500.json", "other_1.json"):
        (d / name).write_text("{}", encoding="utf-8")

    purged = _shared.prune_digest_files("gdelt_gkg", keep=1)

    assert purged == ["gdelt_gkg_20260101000000.json"]
    survivors = sorted(p.name for p in d.iterdir())
    assert survivors == ["gdelt_gkg_20260101001500.json", "other_1.json"]  # other source untouched


def test_unified_cli_dispatches_ingest_and_runs_categories() -> None:
    from algent_backend.cli.__main__ import _CATEGORIES

    assert set(_CATEGORIES) == {"runs", "ingest"}
    ingest_commands = {m.add_parser.__module__.rsplit(".", 1)[-1] for m in _CATEGORIES["ingest"][1]}
    assert {"fetch", "insights", "sample", "digest", "sources"} <= ingest_commands


# -- candidate extraction -----------------------------------------------------


def test_extract_candidates_covers_themes_and_entities_with_min_count() -> None:
    records = [
        _rec(themes=["ECON_X"], persons=["jane doe"], organizations=["acme"], source_name="a.com"),
        _rec(themes=["ECON_X"], persons=["jane doe"], source_name="b.com"),
        _rec(themes=["ECON_X"], language="spa", source_name="c.com"),
        _rec(themes=["RARE"]),  # below min_count -> dropped
    ]
    stats = {s.full_key: s for s in extract_candidates(records, min_count=2)}

    assert "theme:ECON_X" in stats and "person:jane doe" in stats
    assert "theme:RARE" not in stats
    econ = stats["theme:ECON_X"]
    assert econ.count == 3 and econ.pillar == "economy"
    assert set(econ.languages) == {"eng", "spa"}
    assert econ.source_spread == 3  # three distinct outlets


def test_extract_candidates_drops_boilerplate_themes() -> None:
    records = [_rec(themes=["TAX_FNCACT", "ECON_X", "CRISISLEX_CRISISLEXREC"]) for _ in range(5)]
    keys = {s.full_key for s in extract_candidates(records, min_count=2)}
    assert keys == {"theme:ECON_X"}  # structural GKG tags filtered out


def test_extract_candidates_drops_media_attribution_entities() -> None:
    records = [
        _rec(organizations=["Getty ImagesCredit", "acme corp"], persons=["jane doe"])
        for _ in range(4)
    ]
    keys = {s.full_key for s in extract_candidates(records, min_count=2)}
    assert keys == {"organization:acme corp", "person:jane doe"}  # photo credit dropped


# -- rolling memory + velocity ------------------------------------------------


def test_rolling_memory_baseline_seen_and_window() -> None:
    mem = RollingMemory(source="s")
    assert not mem.has_history and mem.baseline("k") == 0.0

    mem = mem.with_batch("b1", {"k": 10}).with_batch("b2", {"k": 20})
    assert mem.has_history and mem.baseline("k") == 15.0
    assert mem.seen("k") and not mem.seen("other")

    trimmed = mem.with_batch("b3", {"k": 30}, window=2)
    assert [b.batch_id for b in trimmed.batches] == ["b2", "b3"]  # oldest dropped


def test_velocity_is_none_without_history_then_flags_rising() -> None:
    records = [_rec(themes=["ECON_X"]) for _ in range(10)]

    first, counts = build_insights(records, source="s", batch_id="b1", memory=RollingMemory("s"))
    econ_first = next(c for c in first.candidates if c.key == "ECON_X")
    assert first.has_velocity_baseline is False and econ_first.velocity is None

    memory = RollingMemory("s").with_batch("b0", {"theme:ECON_X": 2})  # was small, now 10
    second, _ = build_insights(records, source="s", batch_id="b1", memory=memory)
    econ_second = next(c for c in second.candidates if c.key == "ECON_X")
    assert econ_second.velocity is not None and econ_second.velocity > 0
    assert econ_second.rising and "rising" in econ_second.reasons


# -- ranking protected quota --------------------------------------------------


def test_select_reserves_quota_for_protected_margins() -> None:
    # Loud English themes (count 5), plus one tiny non-English-only outsider (count 3).
    loud = [_rec(themes=[f"LOUD_{i}"], source_name=f"{i}.com") for i in range(20)]
    outsider = [_rec(themes=["OUTSIDER"], language="ukr") for _ in range(3)]
    stats = extract_candidates(loud * 5 + outsider, min_count=3)
    scored = ranking.score_candidates(stats, RollingMemory("s"))

    without_quota = ranking.select(scored, top=5, quota=0)
    with_quota = ranking.select(scored, top=5, quota=2)

    keys_no = {s.candidate.stats.key for s in without_quota}
    keys_yes = {s.candidate.stats.key for s in with_quota}
    assert "OUTSIDER" not in keys_no  # loud incumbents win on raw score
    assert "OUTSIDER" in keys_yes  # quota rescues the non-English margin


def test_select_collapses_co_occurring_candidates() -> None:
    # Two entities that always appear together (same 5 records) = one story.
    records = [_rec(persons=["alice"], organizations=["acme corp"]) for _ in range(5)]
    stats = extract_candidates(records, min_count=3)
    selections = ranking.select(ranking.score_candidates(stats, RollingMemory("s")), top=10, quota=0)

    assert len(selections) == 1  # collapsed to a single representative
    rep = selections[0]
    assert rep.related  # the co-occurring entity folded in as related context


# -- sampling -----------------------------------------------------------------


def test_stratified_reservoir_balances_across_languages() -> None:
    import random

    items = [{"lang": "en"} for _ in range(1000)] + [{"lang": "sw"} for _ in range(3)]
    picked = sampling.stratified_reservoir(
        items, size=10, key=lambda r: r["lang"], per_key_cap=5, rng=random.Random(0)
    )
    langs = {r["lang"] for r in picked}
    assert "sw" in langs  # the rare language survives a 1000:3 imbalance


# -- CLI: insights + sample ---------------------------------------------------


def test_insights_cli_writes_report_and_updates_memory(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    records = [_rec(themes=["ECON_X"], persons=["jane doe"]) for _ in range(5)]
    monkeypatch.setitem(insights_cmd._FETCHERS, "gdelt_gkg", lambda: ("20260101000000", records))

    assert insights_cmd.run(_ns(source="gdelt_gkg", keep=1, warmup=0)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["batch_id"] == "20260101000000"
    assert out["has_velocity_baseline"] is False
    assert os.path.exists(out["report_path"])

    # Memory now carries this batch, so a second run has a baseline.
    mem = load_memory("gdelt_gkg", _shared.memory_dir())
    assert mem.has_history and mem.seen("theme:ECON_X")


def test_insights_warmup_backfills_memory_from_preceding_batches(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    latest = [_rec(themes=["ECON_X"]) for _ in range(10)]
    monkeypatch.setitem(insights_cmd._FETCHERS, "gdelt_gkg", lambda: ("20260101010000", latest))
    # Each preceding batch had ECON_X small (count 2) -> latest (10) reads as rising.
    monkeypatch.setitem(
        insights_cmd._BATCH_FETCHERS,
        "gdelt_gkg",
        lambda bid: (bid, [_rec(themes=["ECON_X"]) for _ in range(2)]),
    )

    assert insights_cmd.run(_ns(source="gdelt_gkg", keep=1, warmup=4)) == 0
    report = json.loads(
        open(tmp_path / "insights" / "gdelt_gkg_20260101010000.json", encoding="utf-8").read()
    )
    assert report["has_velocity_baseline"] is True
    econ = next(c for c in report["candidates"] if c["key"] == "ECON_X")
    assert econ["velocity"] is not None and econ["velocity"] > 0 and econ["rising"]


def test_preceding_batch_ids_step_back_15_minutes() -> None:
    ids = insights_cmd._preceding_batch_ids("20260101010000", 3)
    assert ids == ["20260101001500", "20260101003000", "20260101004500"]  # oldest first


def test_sample_cli_writes_stratified_slice(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(_shared._OUTPUT_ENV, str(tmp_path))
    stream = (
        {"ngram": f"w{i}", "lang": "en", "pre": "a", "post": "b", "url": "u"} for i in range(50)
    )
    monkeypatch.setitem(sample_cmd._STREAMERS, "gdelt_ngrams", lambda: ("20260101000100", stream))

    assert sample_cmd.run(_ns(source="gdelt_ngrams", size=5, keep=1)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["size"] == 5
    written = json.loads(open(out["sample_path"], encoding="utf-8").read())
    assert len(written["records"]) == 5
    assert written["records"][0]["text"]  # snippet assembled from pre/post


# -- live smokes (opt-in) -----------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("ALGENT_LIVE_GKG") != "1",
    reason="live GDELT fetch; set ALGENT_LIVE_GKG=1 to run",
)
def test_gkg_fetch_smoke() -> None:
    batch_id, records = gdelt_gkg.fetch_latest()
    assert len(batch_id) == 14 and batch_id.isdigit()
    assert len(records) > 100


@pytest.mark.skipif(
    os.environ.get("ALGENT_LIVE_NGRAMS") != "1",
    reason="live GDELT fetch; set ALGENT_LIVE_NGRAMS=1 to run",
)
def test_ngrams_fetch_smoke() -> None:
    packet = gdelt_ngrams.fetch_latest_raw()
    assert len(packet.batch_id) == 14 and packet.batch_id.isdigit()
    assert packet.parts[0].record_count > 100


class _ns:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
