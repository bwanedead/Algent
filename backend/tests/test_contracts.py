"""Versioned contracts: the registry declarations, the shapes, the examples, the stamp on publish, and the writers' own output against the shapes."""

from __future__ import annotations

import gzip
import json
from datetime import date

import pytest

from algent_backend import contracts
from algent_backend.contracts import resolve, spec
from algent_backend.contracts.examples import EXAMPLES
from algent_backend.contracts.shapes import SHAPES
from algent_backend.ops.products import views
from algent_backend.publishing import doc_store, object_docs

ALL = {c.schema: c for _pid, c in resolve.contracts()}


# ── the shape language ─────────────────────────────────────────────────────────────────────────
def test_the_spec_language_catches_renames_retypes_and_allows_additions() -> None:
    s = {"rows": [{"id": "str", "n": "int", "tag?": "str", "at": "str|null"}], "kind": "in:a,b"}
    ok = {"rows": [{"id": "x", "n": 1, "at": None, "extra": 1}], "kind": "a", "more": True}
    assert spec.validate(ok, s) == []
    assert spec.validate({"rows": [{"ident": "x", "n": 1, "at": None}], "kind": "a"}, s) == ["$.rows[0].id: missing"]
    assert spec.validate({"rows": [{"id": "x", "n": "1", "at": None}], "kind": "a"}, s) == ["$.rows[0].n: expected int, got str"]
    assert spec.validate({"rows": [{"id": "x", "n": True, "at": None}], "kind": "c"}, s)[:1] == ["$.rows[0].n: expected int, got bool"]
    assert spec.validate({"windows": {"7": {}, "30": 1}}, {"windows": {"*": "obj"}}) == ["$.windows.30: expected obj, got int"]


# ── the registry and the shapes agree ──────────────────────────────────────────────────────────
def test_every_contract_has_a_shape_and_every_shape_a_contract() -> None:
    assert set(SHAPES) == set(ALL), (set(SHAPES) ^ set(ALL))
    for pid, c in resolve.contracts():
        assert c.version >= 1 and all(a < c.version for a in c.accepts) and c.paths
        p = views.by_id(pid)
        assert p.publishes, f"{pid} declares contracts but publishes nothing"


def test_schema_ids_are_unique_and_every_pattern_resolves_to_exactly_its_contract() -> None:
    owners: dict[str, str] = {}
    for pid, c in resolve.contracts():
        assert owners.setdefault(c.schema, pid) == pid, f"{c.schema} is declared by two products"
        for glob in c.paths:
            concrete = glob.replace("**", "a/b").replace("*", "x")
            assert resolve.find(concrete)[1].schema == c.schema, (glob, resolve.find(concrete))


def test_the_most_specific_pattern_wins() -> None:
    assert resolve.find("theaters/index.json")[1].schema == "ohmega.dossier.index"
    assert resolve.find("theaters/thr_x.json")[1].schema == "ohmega.dossier"
    assert resolve.find("docs/live/vessels.json.gz")[1].schema == "ohmega.live.vessels"
    assert resolve.find("live/tiles/index.json")[1].schema == "ohmega.live.tiles.index"
    assert resolve.find("live/tiles/r1c1.json")[1].schema == "ohmega.live.tile"
    assert resolve.find("views/entity/org/irgc.json")[1].schema == "ohmega.view.entity"
    assert resolve.find("views/home.json")[1].schema == "ohmega.view.home"
    assert resolve.find("nothing/here.json") is None


def test_the_examples_cover_every_non_view_schema_and_fit_their_shape() -> None:
    assert set(EXAMPLES) == {s for s in ALL if not s.startswith("ohmega.view.")}
    for schema, (path, doc) in EXAMPLES.items():
        assert resolve.find(path)[1].schema == schema, (schema, path)
        assert doc["schema"] == ALL[schema].stamp
        assert spec.validate(doc, SHAPES[schema]) == [], schema


def test_a_view_family_takes_its_stamp_from_the_registry() -> None:
    from algent_backend.views import flags

    assert contracts.view_schema("country") == "ohmega.view.country/1"
    assert set(flags.BUDGET_BYTES) == {s.removeprefix("ohmega.view.") for s in ALL if s.startswith("ohmega.view.")}
    with pytest.raises(KeyError):
        contracts.view_schema("nope")


def test_the_generated_site_table_is_checked_in_and_current() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "sites" / "ohmega-monster" / "lib" / "contracts.json"
    assert json.loads(path.read_text(encoding="utf-8")) == contracts.site_table(), "regenerate: python -m algent_backend.cli newsroom contracts table --write"
    row = next(r for r in contracts.site_table()["contracts"] if r["schema"] == "ohmega.track-record")
    assert row["version"] == 2 and row["accepts"] == [1, 2]


# ── the stamp on publish ───────────────────────────────────────────────────────────────────────
def test_publishing_stamps_the_schema_and_costs_no_reupload_for_a_major_1_document() -> None:
    body = {"rows": []}
    plain, stamped = doc_store.pack("sanctions/recent.json", body), doc_store.pack("sanctions/recent.json", body, "ohmega.sanctions/1")
    assert plain.sha256 == stamped.sha256, "adding a v1 stamp must not look like a change"
    assert json.loads(stamped.raw)["schema"] == "ohmega.sanctions/1" and "schema" not in json.loads(plain.raw)
    assert doc_store.pack("data/track-record.json", body, "ohmega.track-record/2").sha256 != doc_store.pack("data/track-record.json", body).sha256, "a major bump re-sends once"


def test_object_docs_stamps_what_it_uploads() -> None:
    sent: dict[str, bytes] = {}

    def http(method, url, headers, body):
        sent[url] = body
        return 200

    res = object_docs.publish({"sanctions/recent.json": {"rows": []}, "calendar/next.json": {"items": []}, "other/none.json": {"a": 1},
                               "views/home.json": {"schema": "ohmega.view.home/1"}}, http=http, names=False)
    assert res["documents"] == 4
    got = {u.split("/docs/")[1]: json.loads(gzip.decompress(b)) for u, b in sent.items()}
    assert got["sanctions/recent.json.gz"]["schema"] == "ohmega.sanctions/1" and got["calendar/next.json.gz"]["schema"] == "ohmega.calendar/1"
    assert "schema" not in got["other/none.json.gz"] and got["views/home.json.gz"]["schema"] == "ohmega.view.home/1"
    assert object_docs.publish({"sanctions/recent.json": {"rows": []}}, http=http, names=False)["documents"] == 0      # unchanged: skipped


def test_a_document_with_its_own_schema_is_left_alone() -> None:
    assert contracts.stamp_for("data/track-record.json", {"schema": "ohmega.track-record/2"}) == ""
    assert contracts.stamp_for("sanctions/recent.json", [1]) == ""
    assert contracts.parse_stamp("ohmega.live.tile/3") == ("ohmega.live.tile", 3) and contracts.parse_stamp("v1") is None


# ── the writers' own output against the shapes ────────────────────────────────────────────────
def _check(docs: dict) -> int:
    n = 0
    for path, body in docs.items():
        hit = resolve.find(path)
        if hit is None:
            continue
        assert spec.validate(body, SHAPES[hit[1].schema]) == [], (path, hit[1].schema)
        n += 1
    return n


def test_the_test_record_the_views_are_built_from_fits_the_shapes() -> None:
    from views_fixture import staged, tables

    assert _check(staged().docs) >= 14
    docs = {k: v for k, v in tables()._docs.items() if k.startswith(("calendar/", "geo/grid"))}
    assert _check(docs) == 2


def test_the_sanctions_calendar_maritime_geo_and_live_builders_fit_the_shapes(tmp_path, monkeypatch) -> None:
    from algent_backend.lookahead import publish as calendar_publish
    from algent_backend.sanctions import publish as sanctions_publish

    assert _check(sanctions_publish.documents(date(2026, 10, 23))) == 1                    # an empty store still yields the recent document
    assert _check(calendar_publish.documents(date(2026, 10, 23))) == 1
    from algent_backend.maritime import publish as maritime_publish

    assert _check(maritime_publish.documents()) >= 3
    from algent_backend.geoledger import site_docs

    assert _check(site_docs.documents()) >= 2
    from algent_backend.live import publish as live_publish

    assert _check(live_publish.documents(with_stats=True, today=date(2026, 10, 23))) == 2


def test_the_status_writer_fits_its_shape() -> None:
    from algent_backend.ops import status

    doc = status.record(views.by_id("sanctions"), "sanctions", True)
    assert spec.validate({"schema": "ohmega.status/1", **doc}, SHAPES["ohmega.status"]) == []


def test_every_view_the_builders_make_fits_its_shape_and_carries_the_registered_stamp(tmp_path) -> None:
    from test_site_views_contract import fixture_views

    built = fixture_views(tmp_path)
    seen = set()
    for key, body in built.items():
        hit = resolve.find(f"views/{key}.json")
        assert hit is not None, key
        assert body["schema"] == hit[1].stamp and spec.validate(body, SHAPES[hit[1].schema]) == [], key
        seen.add(hit[1].schema)
    assert seen >= {f"ohmega.view.{f}" for f in ("country", "situation", "situations", "entity", "event", "home", "hud", "daily-hub", "graph", "search-index", "series", "series-index", "manifest")}
