"""Publishing views: an unchanged view is byte-identical (kept built_at) and so costs no upload; the local store is written first and pruned; a dry run sends nothing;
the R2 guard still refuses past its limit; and the Class A estimate for a full upload."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta

import pytest
from views_fixture import context

from algent_backend.publishing import object_budget, object_store
from algent_backend.views import build, publish

R2 = {"R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "AKID", "R2_SECRET_ACCESS_KEY": "sek", "R2_BUCKET": "ohmega", "R2_PUBLIC_BASE": "https://pub.example"}
T0 = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


class Bucket:
    def __init__(self) -> None:
        self.puts: list[str] = []
        self.objects: dict[str, bytes] = {}

    def __call__(self, method, url, headers, body):
        if method == "PUT":
            key = url.split("/ohmega/", 1)[1]
            self.puts.append(key)
            self.objects[key] = body
        return 200, {}, b""


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for k, v in R2.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ALGENT_PUBLISH_HELD", str(tmp_path / "held"))
    monkeypatch.setenv(publish.STORE_ENV, str(tmp_path / "views_store"))
    bucket = Bucket()
    monkeypatch.setattr(object_store, "default_call", bucket)
    return tmp_path, bucket


def run(only=None, now=T0):
    res = build.build_all(context(), only)
    assert not res.errors, res.errors
    return res, publish.publish(res.ok_views(), complete=only is None, now=now)


def test_a_second_build_of_the_same_record_sends_nothing(env):
    _, bucket = env
    res, out = run()
    assert out["upload"]["ok"] and out["upload"]["documents"] == len(res.views) and len(bucket.puts) == len(res.views)
    assert "docs/views/country/IR.json.gz" in bucket.objects and "docs/views/manifest.json.gz" in bucket.objects
    body = json.loads(gzip.decompress(bucket.objects["docs/views/country/IR.json.gz"]))
    assert body["built_at"] == T0.isoformat(timespec="seconds") and body["schema"] == "ohmega.view.country/1"
    first = len(bucket.puts)
    _, again = run(now=T0 + timedelta(hours=4))                                  # the same record, four hours later
    assert again["upload"]["documents"] == 0 and again["upload"]["unchanged"] == len(res.views) and len(bucket.puts) == first
    assert again["store"]["wrote"] == 0 and again["store"]["unchanged"] == len(res.views)


def test_a_changed_view_gets_a_new_built_at_and_is_the_only_upload(env):
    _, bucket = env
    run()
    ctx = context()
    ctx.tables._docs["calendar/next.json"]["items"][0]["title"] = "Gulf summit moved"
    res = build.build_all(ctx)
    out = publish.publish(res.ok_views(), now=T0 + timedelta(hours=4))
    sent = {k for k in bucket.puts[len(res.views):]}
    assert sent and sent <= {"docs/views/country/IR.json.gz", "docs/views/country/SA.json.gz", "docs/views/home.json.gz", "docs/views/hud.json.gz", "docs/views/manifest.json.gz"}
    assert out["upload"]["documents"] == len(sent)
    ir = json.loads(gzip.decompress(bucket.objects["docs/views/country/IR.json.gz"]))
    fr = json.loads(publish_store(env, "country/FR"))
    assert ir["built_at"] == (T0 + timedelta(hours=4)).isoformat(timespec="seconds") and fr["built_at"] == T0.isoformat(timespec="seconds")


def publish_store(env, key):
    return (env[0] / "views_store" / f"{key}.json").read_text(encoding="utf-8")


def test_the_server_holds_every_view_before_it_is_sent_and_prunes_what_is_gone(env):
    tmp, _ = env
    run()
    assert (tmp / "views_store" / "country" / "IR.json").is_file() and (tmp / "views_store" / "manifest.json").is_file()
    stale = tmp / "views_store" / "situation" / "thr_gone.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("{}", encoding="utf-8")
    run(["home"])                                                                  # a partial build never prunes
    assert stale.is_file()
    run()
    assert not stale.exists() and not stale.parent.exists() or not any(stale.parent.glob("thr_gone*"))


def test_a_dry_run_reports_the_upload_and_records_nothing(env):
    tmp, bucket = env
    res = build.build_all(context())
    out = publish.publish(res.ok_views(), dry_run=True, now=T0)
    assert out["dry_run"] and out["would_upload"] == len(res.views) and out["bytes_gz"] > 0 and not bucket.puts
    assert not (tmp / "views_store").exists() and not (tmp / "held" / "doc_hashes.json").exists()
    est = publish.estimate(res.views)
    assert est["class_a"] == len(res.views) and est["gz_bytes"] < est["raw_bytes"]


def test_the_r2_guard_refuses_a_publish_past_its_limit_and_the_view_is_retried_later(env, monkeypatch):
    _, bucket = env
    monkeypatch.setattr(object_budget.flags, "R2_FREE_CLASS_A", 3)                 # a hard stop after 2 operations
    res = build.build_all(context(), ["home", "hud", "daily-hub"])
    out = publish.publish(res.ok_views(), complete=False, now=T0)
    assert out["upload"]["ok"] is False and len(bucket.puts) < len(res.views)
    monkeypatch.setattr(object_budget.flags, "R2_FREE_CLASS_A", 1_000_000)
    again = publish.publish(build.build_all(context(), ["home", "hud", "daily-hub"]).ok_views(), complete=False, now=T0 + timedelta(minutes=30))
    assert again["upload"]["ok"] and len(set(bucket.puts)) == len(res.views)       # everything lands once the budget allows


def test_an_over_budget_view_is_reported_and_not_published(env, monkeypatch):
    _, bucket = env
    from algent_backend.views import flags

    monkeypatch.setitem(flags.BUDGET_BYTES, "daily-hub", 200)
    res = build.build_all(context(), ["daily-hub", "home"])
    assert res.over_budget == ["views/daily-hub.json"] and any("byte budget" in e for e in res.errors)
    publish.publish(res.ok_views(), complete=False, now=T0)
    assert "docs/views/daily-hub.json.gz" not in bucket.objects and "docs/views/home.json.gz" in bucket.objects
