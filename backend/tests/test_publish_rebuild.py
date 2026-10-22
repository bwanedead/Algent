"""`newsroom publish rebuild-all`: every document from the local stores, idempotent, dry run sends nothing. Offline (a fake bucket)."""

from __future__ import annotations

import gzip
import json
from types import SimpleNamespace

import pytest

from algent_backend.cli.newsroom import publish as cli
from algent_backend.publishing import object_store, rebuild

R2 = {"R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "AKID", "R2_SECRET_ACCESS_KEY": "sek", "R2_BUCKET": "ohmega", "R2_PUBLIC_BASE": "https://pub.example"}
ONLY = ["site-documents", "articles", "images", "sanctions", "calendar", "maritime", "live", "geoledger"]


class Bucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def __call__(self, method, url, headers, body):
        if method == "PUT":
            self.objects[url.split("/ohmega/", 1)[1]] = body
        return 200, {}, b""


@pytest.fixture
def site(tmp_path, monkeypatch):
    for k, v in R2.items():
        monkeypatch.setenv(k, v)
    for env in ("MARITIME", "LIVE", "SANCTIONS", "CALENDAR", "GEOLEDGER"):
        monkeypatch.setenv(f"ALGENT_{env}_STORE", str(tmp_path / env.lower()))
    bucket = Bucket()
    monkeypatch.setattr(object_store, "default_call", bucket)
    root = tmp_path / "site"
    files = {"content/intel/daily/geopolitics/2026-10-01.json": {"a": 1}, "content/intel/record.json": {"r": 1}, "content/radar/2026-10-01-1000.json": {"x": 1},
             "public/data/index.json": {"i": 1}}
    for rel, body in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(body), encoding="utf-8")
    art = root / "content" / "articles"
    art.mkdir(parents=True)
    (art / "hello.md").write_text("---\ntitle: Hello\nstatus: publishable\npublished_at: '2026-10-01T10:00:00+00:00'\n---\nbody\n", encoding="utf-8")
    img = root / "public" / "analytics" / "hello"
    img.mkdir(parents=True)
    (img / "hero.webp").write_bytes(b"img")
    return root, bucket


def test_dry_run_counts_what_would_be_sent_and_sends_nothing(site) -> None:
    root, bucket = site
    rep = rebuild.run(dry_run=True, only=ONLY, roots=[root])
    assert rep["ok"] is True and rep["dry_run"] is True and not bucket.objects
    docs = rep["steps"]["site-documents"]
    assert docs["of"] == 4 and docs["would_upload"] == 4 and docs["bytes_gz"] > 0
    assert rep["steps"]["articles"]["of"] == 2 and rep["steps"]["images"]["files"] == 1          # the article + the index; one image
    assert not (object_store.held_dir() / "doc_hashes.json").exists()                           # a dry run records nothing


def test_rebuild_publishes_everything_then_a_second_run_sends_nothing(site) -> None:
    root, bucket = site
    rep = rebuild.run(only=ONLY, roots=[root])
    assert rep["ok"] is True
    keys = set(bucket.objects)
    assert {"docs/daily/geopolitics/2026-10-01.json.gz", "docs/record.json.gz", "docs/radar/2026-10-01-1000.json.gz", "docs/data/index.json.gz",
            "docs/articles/hello.json.gz", "docs/articles/index.json.gz", "analytics/hello/hero.webp", "docs/_names/daily/geopolitics.json.gz"} <= keys
    assert json.loads(gzip.decompress(bucket.objects["docs/_names/daily/geopolitics.json.gz"])) == ["2026-10-01.json"]
    first = len(bucket.objects)
    again = rebuild.run(only=ONLY, roots=[root])
    assert again["ok"] is True and again["steps"]["site-documents"]["documents"] == 0 and again["steps"]["site-documents"]["unchanged"] == 4
    assert again["steps"]["images"]["assets"] == 0 and again["steps"]["images"]["skipped"] == 1
    assert len(bucket.objects) == first


def test_a_broken_step_is_reported_and_the_rest_still_run(site, monkeypatch) -> None:
    root, bucket = site
    from algent_backend.sanctions import publish as sanctions_publish

    monkeypatch.setattr(sanctions_publish, "documents", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("store unreadable")))
    rep = rebuild.run(only=["sanctions", "site-documents"], roots=[root])
    assert rep["steps"]["sanctions"]["ok"] is False and "store unreadable" in rep["steps"]["sanctions"]["note"]
    assert rep["steps"]["site-documents"]["documents"] == 4 and rep["ok"] is False


def test_the_cli_prints_one_json_document(site, capsys, monkeypatch) -> None:
    root, _ = site
    monkeypatch.setattr(rebuild, "site_roots", lambda root_=None: [root])
    code = cli.run_rebuild_all(SimpleNamespace(dry_run=True, only="site-documents"))
    assert code == 0 and json.loads(capsys.readouterr().out)["steps"]["site-documents"]["would_upload"] == 4


def test_the_guard_stops_a_rebuild_at_the_hard_stop_without_raising(site, monkeypatch) -> None:
    from algent_backend.database import flags

    root, bucket = site
    monkeypatch.setattr(flags, "R2_FREE_CLASS_A", 10)
    monkeypatch.setattr(flags, "R2_DAILY_STOP_MULT", 100.0)
    rep = rebuild.run(only=["site-documents", "articles"], roots=[root])
    assert rep["ok"] is False and len(bucket.objects) <= 9                                       # 90% of 10 operations, then refusals
