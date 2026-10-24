"""The staging channel: ALGENT_PUBLISH_TARGET=staging puts every key under ``staging/`` through the one document path, keeps its hashes apart from
production, holds its own lower allowance, prunes by age, and ``stage-from-prod`` copies a sample from the local stores without reading the bucket back.
Offline (a fake bucket)."""

from __future__ import annotations

import gzip
import json

import pytest

from algent_backend.cli.newsroom import publish as cli
from algent_backend.database import flags
from algent_backend.publishing import object_docs, object_store, rebuild, staging, staging_docs
from algent_backend.views import publish as view_publish

R2 = {"R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "AKID", "R2_SECRET_ACCESS_KEY": "sek", "R2_BUCKET": "ohmega", "R2_PUBLIC_BASE": "https://pub.example"}


class Bucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.reads: list[str] = []
        self.deleted: list[str] = []

    def __call__(self, method, url, headers, body):
        key = url.split("/ohmega/", 1)[1] if "/ohmega/" in url else ""
        if method == "PUT":
            self.objects[key] = body
        elif method == "DELETE":
            self.objects.pop(key, None)
            self.deleted.append(key)
            return 204, {}, b""
        elif method in ("GET", "HEAD"):
            self.reads.append(f"{method} {key}")
            return 404, {}, b""
        return 200, {}, b""


@pytest.fixture
def env(tmp_path, monkeypatch):
    for k, v in R2.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ALGENT_PUBLISH_HELD", str(tmp_path / "held"))
    monkeypatch.setenv(view_publish.STORE_ENV, str(tmp_path / "views_store"))
    monkeypatch.delenv(staging.ENV, raising=False)
    bucket = Bucket()
    monkeypatch.setattr(object_store, "default_call", bucket)
    return tmp_path, bucket


def site_root(tmp_path):
    root = tmp_path / "site"
    files = {"content/intel/daily/geopolitics/2026-10-01.json": {"d": 1}, "content/intel/daily/geopolitics/2026-10-02.json": {"d": 2},
             "content/intel/daily/geopolitics/2026-10-03.json": {"d": 3}, "content/intel/daily/geopolitics/2026-10-04.json": {"d": 4},
             "content/intel/daily/geopolitics/2026-10-05.json": {"d": 5}, "content/intel/record.json": {"r": 1}}
    for rel, body in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(body), encoding="utf-8")
    return root


def test_staging_target_puts_every_key_under_the_prefix_and_production_is_untouched(env, monkeypatch) -> None:
    tmp_path, bucket = env
    root = site_root(tmp_path)
    monkeypatch.setenv(staging.ENV, "staging")
    rep = rebuild.run(only=["site-documents"], roots=[root])
    assert rep["ok"] is True
    assert bucket.objects and all(k.startswith("staging/") for k in bucket.objects)
    assert "staging/docs/record.json.gz" in bucket.objects and "staging/docs/_names/daily/geopolitics.json.gz" in bucket.objects
    assert not bucket.reads                                                                  # nothing is read back from the bucket
    assert object_store.public_base() == "https://pub.example/staging"                       # what the preview's NEXT_PUBLIC_DATA_BASE must equal
    staged = len(bucket.objects)

    monkeypatch.delenv(staging.ENV)                                                           # production: its hashes are separate, so it sends everything once
    rebuild.run(only=["site-documents"], roots=[root])
    prod = {k for k in bucket.objects if not k.startswith("staging/")}
    assert "docs/record.json.gz" in prod and len(bucket.objects) == staged + len(prod)
    again = len(bucket.objects)
    rebuild.run(only=["site-documents"], roots=[root])                                       # hash-skipped on both sides
    assert len(bucket.objects) == again


def test_unknown_target_publishes_nothing(env, monkeypatch) -> None:
    tmp_path, bucket = env
    monkeypatch.setenv(staging.ENV, "stagng")                                                 # a typo must not fall through to production
    assert object_store.select() is None
    res = object_docs.publish({"record.json": {"r": 1}})
    assert res["ok"] is False and not bucket.objects


def test_cli_target_flag_sets_the_target(env, monkeypatch) -> None:
    tmp_path, bucket = env
    ns = type("A", (), {"target": "staging"})()
    cli.apply_target(ns)
    assert staging.is_staging()
    cli.apply_target(type("A", (), {"target": "production"})())
    assert not staging.is_staging()


def test_staging_allowance_refuses_past_its_daily_operations(env, monkeypatch) -> None:
    tmp_path, bucket = env
    monkeypatch.setattr(flags, "STAGING_CLASS_A_PER_DAY", 2)
    monkeypatch.setenv(staging.ENV, "staging")
    res = object_docs.publish({f"doc{i}.json": {"i": i} for i in range(5)}, names=False)
    assert res["ok"] is False and res["documents"] == 2 and len(bucket.objects) == 2        # the rest are retried when the allowance allows


def test_staging_allowance_refuses_past_its_bytes(env, monkeypatch) -> None:
    tmp_path, bucket = env
    monkeypatch.setattr(flags, "STAGING_MAX_BYTES", 10)
    monkeypatch.setenv(staging.ENV, "staging")
    res = object_docs.publish({"big.json": {"x": "y" * 500}}, names=False)
    assert res["ok"] is False and not bucket.objects


def test_prune_deletes_old_staged_objects_and_forgets_their_hashes(env, monkeypatch) -> None:
    tmp_path, bucket = env
    docs = {"daily/geopolitics/2026-10-01.json": {"a": 1}, "record.json": {"r": 1}}
    with staging.using(staging.STAGING):
        assert object_docs.publish(docs, names=False)["documents"] == 2
        led = staging.ledger()
        old = "staging/docs/record.json.gz"
        led._state["objects"][old][0] = "2020-01-01T00:00:00+00:00"          # written long ago
        dry = staging.prune(dry_run=True)
    assert dry["stale"] == 1 and dry["deleted"] == 0 and old in bucket.objects
    rep = staging.prune()
    assert rep["deleted"] == 1 and rep["ok"] is True and bucket.deleted == [old] and old not in bucket.objects
    assert "staging/docs/daily/geopolitics/2026-10-01.json.gz" in bucket.objects            # the fresh one stays
    with staging.using(staging.STAGING):
        again = object_docs.publish(docs, names=False)
    assert again["documents"] == 1 and old in bucket.objects                                 # the pruned one is re-sent, the kept one skipped


def test_sample_keeps_the_newest_per_directory_and_every_index() -> None:
    docs = {f"daily/geopolitics/2026-10-0{i}.json": i for i in range(1, 6)}
    docs.update({"daily/geopolitics/index.json": 0, "record.json": 1, "theaters/index.json": 2, **{f"theaters/t{i:02d}.json": i for i in range(15)}})
    got = staging_docs.sample(docs)
    assert sorted(p for p in got if p.startswith("daily/")) == ["daily/geopolitics/2026-10-03.json", "daily/geopolitics/2026-10-04.json",
                                                              "daily/geopolitics/2026-10-05.json", "daily/geopolitics/index.json"]
    assert "record.json" in got and "theaters/index.json" in got
    assert len([p for p in got if p.startswith("theaters/t")]) == 10


def test_stage_from_prod_copies_a_sample_from_local_stores_and_is_hash_skipped(env, monkeypatch) -> None:
    tmp_path, bucket = env
    root = site_root(tmp_path)
    views = tmp_path / "views_store"
    for key, body in {"home": {"h": 1}, "country/AA": {"x": "y" * 50}, "country/BB": {"x": "y" * 500}, "_state": {}}.items():
        f = views / f"{key}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(flags, "STAGING_VIEW_CAPS", {"country": 1})
    rep = staging_docs.stage_from_prod(only=["site-documents", "views"], roots=[root])
    assert rep["ok"] is True and rep["target"] == "staging"
    assert all(k.startswith("staging/") for k in bucket.objects) and not bucket.reads
    assert "staging/docs/views/home.json.gz" in bucket.objects and "staging/docs/views/country/BB.json.gz" in bucket.objects   # the largest country only
    assert "staging/docs/views/country/AA.json.gz" not in bucket.objects
    assert "staging/docs/daily/geopolitics/2026-10-01.json.gz" not in bucket.objects and "staging/docs/daily/geopolitics/2026-10-05.json.gz" in bucket.objects
    assert json.loads(gzip.decompress(bucket.objects["staging/docs/views/home.json.gz"])) == {"h": 1, "schema": "ohmega.view.home/1"}
    assert not staging.is_staging()                                                          # the target is restored after the call
    n = len(bucket.objects)
    again = staging_docs.stage_from_prod(only=["site-documents", "views"], roots=[root])
    assert again["ok"] is True and len(bucket.objects) == n


def test_staging_views_store_is_separate_from_production(env, monkeypatch) -> None:
    tmp_path, _ = env
    assert view_publish.store_dir() == tmp_path / "views_store"
    monkeypatch.setenv(staging.ENV, "staging")
    assert view_publish.store_dir() == tmp_path / "views_store_staging"
    assert view_publish.store_dir(staging.PRODUCTION) == tmp_path / "views_store"
