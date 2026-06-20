"""
Offline tests for the data-ingestion pipeline (GKG → digest).

No network: the GKG row parser is exercised on a synthetic tab-separated batch,
and the lenses/pillars/digest are pure functions over hand-built records. The
live fetch path is covered by ``test_gkg_fetch_smoke`` only when explicitly
enabled, so the default suite stays hermetic.
"""

from __future__ import annotations

import json
import os

import pytest

from algent_backend.data_ingestion.cli import ingest
from algent_backend.data_ingestion.news_production.discovery import lenses
from algent_backend.data_ingestion.news_production.discovery.digest import build_digest
from algent_backend.data_ingestion.news_production.discovery.pillars import pillar_for_theme
from algent_backend.data_ingestion.news_production.sources import gdelt_gkg
from algent_backend.data_ingestion.news_production.sources.records import GkgRecord


def _rec(language="eng", themes=(), tone=None, **kw) -> GkgRecord:
    return GkgRecord(
        record_id=kw.get("record_id", "r"),
        url=kw.get("url", "http://x"),
        source_name=kw.get("source_name", "x.com"),
        language=language,
        themes=tuple(themes),
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
    import io
    import zipfile

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


# -- CLI ----------------------------------------------------------------------


def test_ingest_cli_writes_digest_and_prints_summary(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv(ingest._OUTPUT_ENV, str(tmp_path))
    monkeypatch.setitem(
        ingest._SOURCES,
        "gdelt_gkg",
        lambda: ("20260101000000", [_rec(themes=["ECON_STOCKMARKET"], tone=1.0)]),
    )

    code = ingest.run(_ns(source="gdelt_gkg"))
    assert code == 0

    out = json.loads(capsys.readouterr().out)
    assert out["batch_id"] == "20260101000000"
    assert out["total_records"] == 1
    assert os.path.exists(out["digest_path"])
    written = json.loads(open(out["digest_path"], encoding="utf-8").read())
    assert written["source"] == "gdelt_gkg"
    assert written["languages"][0]["language"] == "eng"


@pytest.mark.skipif(
    os.environ.get("ALGENT_LIVE_GKG") != "1",
    reason="live GDELT fetch; set ALGENT_LIVE_GKG=1 to run",
)
def test_gkg_fetch_smoke() -> None:
    batch_id, records = gdelt_gkg.fetch_latest()
    assert len(batch_id) == 14 and batch_id.isdigit()
    assert len(records) > 100


class _ns:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)
