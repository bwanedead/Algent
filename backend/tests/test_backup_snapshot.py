"""The R2 snapshot: built from the backup coverage list, uploaded to the private bucket, thinned 14/8/12, restored and verified. Offline (a fake S3)."""

from __future__ import annotations

import gzip
import io
import json
import tarfile
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from algent_backend.data_backup import flags, snapshot, sync
from algent_backend.publishing.object_budget import Meter
from algent_backend.publishing.object_store import R2Store, select_backup

NOW = datetime(2026, 10, 23, 6, 40, tzinfo=UTC)


class FakeS3:
    """Just enough of the S3 API for put / get / delete / list-v2 on one bucket."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def __call__(self, method: str, url: str, headers: dict, body: bytes):
        parts = urllib.parse.urlsplit(url)
        key = urllib.parse.unquote(parts.path).split("/", 2)[2] if parts.path.count("/") >= 2 else ""
        if method == "PUT":
            self.objects[key] = body
            return 200, {}, b""
        if method == "DELETE":
            self.objects.pop(key, None)
            return 204, {}, b""
        if method == "GET" and not key:
            prefix = urllib.parse.parse_qs(parts.query).get("prefix", [""])[0]
            rows = "".join(f"<Contents><Key>{k}</Key><Size>{len(v)}</Size></Contents>" for k, v in sorted(self.objects.items()) if k.startswith(prefix))
            return 200, {}, f"<ListBucketResult><IsTruncated>false</IsTruncated>{rows}</ListBucketResult>".encode()
        if method == "GET":
            return (200, {}, self.objects[key]) if key in self.objects else (404, {}, b"")
        return 405, {}, b""


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_PUBLISH_HELD", str(tmp_path / "held"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    s3 = FakeS3()
    store = R2Store("acct", "k", "s", "private-backups", "", call=s3, meter=Meter(tmp_path / "usage.json"))
    sources = {"pulse_store": tmp_path / "pulse", "intel_store": tmp_path / "intel", "empty_store": tmp_path / "nothing"}
    (tmp_path / "pulse" / "log").mkdir(parents=True)
    (tmp_path / "pulse" / "log" / "a.jsonl").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "pulse" / "log" / "partial.tmp").write_text("half written", encoding="utf-8")
    (tmp_path / "intel" / "2026-10-22").mkdir(parents=True)
    (tmp_path / "intel" / "2026-10-22" / "daily.json").write_text('{"x": 1}', encoding="utf-8")
    return store, s3, sources, tmp_path


def test_a_snapshot_uploads_the_stores_and_a_manifest_and_the_drill_verifies_them(env) -> None:
    store, s3, sources, tmp = env
    res = snapshot.snapshot(store, now=NOW, sources=sources)
    assert res["ok"] and res["files"] == 2 and res["stores"] == 2                     # .tmp skipped, absent store skipped
    assert sorted(s3.objects) == ["backups/daily/2026-10-23.manifest.json.gz", "backups/daily/2026-10-23.tar.gz"]
    names = tarfile.open(fileobj=io.BytesIO(s3.objects["backups/daily/2026-10-23.tar.gz"]), mode="r:gz").getnames()
    assert sorted(names) == ["intel_store/2026-10-22/daily.json", "pulse_store/log/a.jsonl"]
    manifest = json.loads(gzip.decompress(s3.objects["backups/daily/2026-10-23.manifest.json.gz"]))
    assert manifest["stores"]["pulse_store"]["files"] == 1 and len(manifest["archive"]["sha256"]) == 64
    drill = snapshot.restore_drill(store, now=NOW)
    assert drill["ok"] and drill["files_checked"] == 2 and drill["date"] == "2026-10-23"
    st = snapshot.read_state()
    assert st["last_snapshot"]["ok"] and st["last_drill"]["ok"] and snapshot.age_hours(NOW + timedelta(hours=5)) == pytest.approx(5.0)
    log = (tmp / "home" / "ops-log.md").read_text(encoding="utf-8")
    assert "snapshot 2026-10-23 ok" in log and "restore-drill ok" in log


def test_the_drill_fails_loudly_on_a_tampered_or_incomplete_archive(env) -> None:
    store, s3, sources, tmp = env
    snapshot.snapshot(store, now=NOW, sources=sources)
    key = "backups/daily/2026-10-23.tar.gz"
    good = s3.objects[key]
    # a file that differs from the manifest (same shape, other bytes), repacked
    buf = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(good), mode="r:gz") as src, tarfile.open(fileobj=buf, mode="w:gz") as out:
        for m in src:
            data = src.extractfile(m).read()
            if m.name.endswith("a.jsonl"):
                data = b"ONE\ntwo\n"
            m.size = len(data)
            out.addfile(m, io.BytesIO(data))
    s3.objects[key] = buf.getvalue()
    bad = snapshot.restore_drill(store, now=NOW)
    assert not bad["ok"] and any("differs" in p or "different" in p for p in bad["problems"])
    assert snapshot.read_state()["last_drill"]["ok"] is False
    assert "restore-drill FAIL" in (tmp / "home" / "ops-log.md").read_text(encoding="utf-8")


def test_restore_unpacks_into_a_new_directory_and_refuses_unsafe_members(env) -> None:
    store, s3, sources, tmp = env
    snapshot.snapshot(store, now=NOW, sources=sources)
    out = snapshot.restore(store, tmp / "restored")
    assert out["ok"] and (tmp / "restored" / "pulse_store" / "log" / "a.jsonl").read_text(encoding="utf-8") == "one\ntwo\n"
    evil = io.BytesIO()
    with tarfile.open(fileobj=evil, mode="w:gz") as t:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    s3.objects["backups/daily/2026-10-24.tar.gz"] = evil.getvalue()
    s3.objects["backups/daily/2026-10-24.manifest.json.gz"] = gzip.compress(json.dumps({"stores": {}, "archive": {"sha256": "x"}}).encode())
    res = snapshot.restore(store, tmp / "evil")
    assert not res["ok"] and not (tmp / "escape.txt").exists()


def test_retention_keeps_14_daily_8_weekly_12_monthly() -> None:
    start = date(2025, 6, 1)
    days = [(start + timedelta(days=i)).isoformat() for i in range(500)]
    keep = snapshot.plan_retention(days)
    newest = sorted(days)[-14:]
    assert set(newest) <= keep and days[-1] in keep
    assert len(keep) <= flags.KEEP_DAILY + flags.KEEP_WEEKLY + flags.KEEP_MONTHLY
    assert len({d[:7] for d in keep}) >= 12                                          # a year of months survives
    assert days[0] not in keep and days[100] not in keep
    sparse = ["2026-10-01", "2026-10-02"]
    assert snapshot.plan_retention(sparse) == set(sparse)                            # nothing is thinned below the limits


def test_snapshot_thins_old_ones_through_the_store_and_never_the_newest(env) -> None:
    store, s3, sources, tmp = env
    for i in range(40):
        d = (date(2026, 8, 1) + timedelta(days=i)).isoformat()
        s3.objects[f"backups/daily/{d}.tar.gz"] = b"x"
        s3.objects[f"backups/daily/{d}.manifest.json.gz"] = b"x"
    res = snapshot.snapshot(store, now=NOW, sources=sources)
    left = snapshot.listing(store)
    assert res["ok"] and left[-1] == "2026-10-23" and len(left) < 41 and "2026-08-01" not in left
    assert all(f"backups/daily/{d}.manifest.json.gz" in s3.objects for d in left)    # manifests follow their archives
    assert not any(k[len(flags.PREFIX):][:10] not in left for k in s3.objects)         # no orphaned manifest or archive of a thinned day


def test_a_refused_upload_is_a_failure_not_a_pass(env, monkeypatch) -> None:
    store, s3, sources, tmp = env
    monkeypatch.setattr(store, "put", lambda *a, **k: 429)
    res = snapshot.snapshot(store, now=NOW, sources=sources)
    assert not res["ok"] and "429" in res["note"] and "last_snapshot" not in snapshot.read_state()


def test_no_bucket_is_reported_and_a_dry_run_needs_none(env) -> None:
    _, _, sources, _ = env
    assert not snapshot.snapshot(None, now=NOW, sources=sources)["ok"]
    dry = snapshot.snapshot(None, now=NOW, dry_run=True, sources=sources)
    assert dry["ok"] and dry["files"] == 2 and dry["archive_bytes"] > 0
    assert select_backup({}) is None
    assert select_backup({"R2_ACCOUNT_ID": "a", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s"}) is None      # the public bucket is never a fallback
    assert select_backup({"R2_ACCOUNT_ID": "a", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s", "R2_BACKUP_BUCKET": "priv"}).bucket == "priv"


def test_the_snapshot_reads_the_same_coverage_list_as_the_git_mirror(monkeypatch, tmp_path) -> None:
    (tmp_path / "f.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sync, "_sources", lambda: {"only_store": tmp_path})
    res = snapshot.snapshot(None, now=NOW, dry_run=True)
    assert res["by_store"] == {"only_store": {"files": 1, "bytes": 2}}


def test_the_git_mirror_skips_files_over_the_threshold(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(flags, "MIRROR_MAX_FILE_BYTES", 10)
    src, dest = tmp_path / "s", tmp_path / "d"
    src.mkdir()
    (src / "small.json").write_text("tiny", encoding="utf-8")
    (src / "big.json").write_text("x" * 50, encoding="utf-8")
    skipped: list[str] = []
    assert sync.mirror({"st": src}, dest, skipped) == 1 and skipped == ["st/big.json"] and not (dest / "st" / "big.json").exists()
