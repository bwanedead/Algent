"""Published assets (Supabase Storage) and the db publish mode: uploader, hash-skip, URLs, migration 006, no git."""

from __future__ import annotations

import json
import re

import pytest

from algent_backend.database import available
from algent_backend.publishing import asset_store, published_db, radar_page, site_git

ENV = {"SUPABASE_URL": "https://abc.supabase.co/", "SUPABASE_SERVICE_ROLE_KEY": "service-key"}


class FakeHttp:
    def __init__(self, status: int = 200) -> None:
        self.calls: list[tuple[str, str, dict, bytes]] = []
        self.status = status

    def __call__(self, method: str, url: str, headers: dict, body: bytes) -> int:
        self.calls.append((method, url, headers, body))
        return self.status


@pytest.fixture
def env(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("ALGENT_DB_PUBLISH", raising=False)


def test_upload_posts_each_object_with_upsert_and_service_key(env, tmp_path) -> None:
    http = FakeHttp()
    out = asset_store.upload({"/analytics/s/hero.webp": b"img", "/analytics/s/c.svg": b"<svg/>"},
                             http=http, manifest=tmp_path / "m.json")
    assert out == {"assets": 2, "skipped": 0, "failed": [], "ok": True}
    method, url, headers, body = http.calls[1]            # sorted: hero.webp is second
    assert method == "POST" and url == "https://abc.supabase.co/storage/v1/object/published-assets/analytics/s/hero.webp"
    assert headers["Authorization"] == "Bearer service-key" and headers["x-upsert"] == "true"
    assert headers["Content-Type"] == "image/webp" and body == b"img"
    assert http.calls[0][2]["Content-Type"] == "image/svg+xml"


def test_unchanged_content_is_skipped_changed_is_reuploaded(env, tmp_path) -> None:
    manifest, http = tmp_path / "m.json", FakeHttp()
    asset_store.upload({"/analytics/s/a.png": b"v1"}, http=http, manifest=manifest)
    again = asset_store.upload({"/analytics/s/a.png": b"v1"}, http=http, manifest=manifest)
    assert again["skipped"] == 1 and again["assets"] == 0 and len(http.calls) == 1
    changed = asset_store.upload({"/analytics/s/a.png": b"v2"}, http=http, manifest=manifest)
    assert changed["assets"] == 1 and len(http.calls) == 2


def test_failed_upload_is_reported_not_raised_and_retried_next_time(env, tmp_path) -> None:
    manifest = tmp_path / "m.json"
    out = asset_store.upload({"/analytics/s/a.png": b"x"}, http=FakeHttp(status=403), manifest=manifest)
    assert out["ok"] is False and out["failed"] == ["/analytics/s/a.png (403)"]
    http = FakeHttp()
    assert asset_store.upload({"/analytics/s/a.png": b"x"}, http=http, manifest=manifest)["assets"] == 1

    def boom(*a):
        raise OSError("network down")

    bad = asset_store.upload({"/analytics/s/b.png": b"x"}, http=boom, manifest=manifest)
    assert bad["ok"] is False and "OSError" in bad["failed"][0]


def test_noop_without_credentials_or_when_paused(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    out = asset_store.upload({"/analytics/s/a.png": b"x"})
    assert out["assets"] == 0 and out["ok"] is True and "off" in out["note"]
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ALGENT_DB_PUBLISH", "0")
    assert asset_store.enabled() is False


def test_public_url_matches_what_the_site_resolves(env) -> None:
    assert asset_store.public_url("/analytics/s/hero.webp") == \
        "https://abc.supabase.co/storage/v1/object/public/published-assets/analytics/s/hero.webp"
    assert asset_store.object_key("/analytics/s/x.svg") == "analytics/s/x.svg"


def test_backfill_uploads_everything_under_public_analytics(env, tmp_path) -> None:
    (tmp_path / "public" / "analytics" / "s").mkdir(parents=True)
    (tmp_path / "public" / "analytics" / "s" / "hero.webp").write_bytes(b"1")
    (tmp_path / "public" / "logo-mark.png").write_bytes(b"2")           # not an article asset: stays in the repo
    http = FakeHttp()
    out = asset_store.backfill(tmp_path, http=http, manifest=tmp_path / "m.json")
    assert out["assets"] == 1 and http.calls[0][1].endswith("/published-assets/analytics/s/hero.webp")


def test_migration_006_exposes_only_the_asset_bucket_for_select() -> None:
    sql = next(p for p in available() if p.stem == "006_published_assets").read_text(encoding="utf-8")
    code = "\n".join(l.split("--")[0] for l in sql.splitlines())
    assert re.findall(r"insert into storage\.buckets", code) and "'published-assets'" in code and "true" in code
    assert re.findall(r"create policy (\w+) on storage\.objects\s+for select to anon", code) == ["published_assets_public_read"]
    assert len(re.findall(r"create policy", code)) == 1                 # no write policy: only the service role writes
    assert "using (bucket_id = 'published-assets')" in code
    assert not re.search(r"\bgrant\b", code) and "create table" not in code


def test_db_mode_flag_defaults_to_git_and_env_overrides(monkeypatch) -> None:
    monkeypatch.delenv("ALGENT_SITE_PUBLISH_VIA", raising=False)
    assert site_git.via_db() is False
    monkeypatch.setenv("ALGENT_SITE_PUBLISH_VIA", "db")
    assert site_git.via_db() is True
    monkeypatch.setenv("ALGENT_SITE_PUBLISH_VIA", "nonsense")
    assert site_git.via_db() is False


def test_db_mode_never_touches_git(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_SITE_PUBLISH_VIA", "db")

    def no_git(*a, **k):
        raise AssertionError("git must not run in db mode")

    monkeypatch.setattr(site_git, "_git", no_git)
    monkeypatch.setattr(published_db, "enabled", lambda: True)
    wt, note = site_git.ensure_worktree(tmp_path)
    assert wt == tmp_path / ".site-live" and wt.is_dir() and "no git" in note
    ok, msg = site_git.commit_and_push(wt, "publish(x)")
    assert ok is True and "no git commit" in msg


def test_db_mode_without_a_database_refuses_instead_of_silently_not_publishing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_SITE_PUBLISH_VIA", "db")
    monkeypatch.setattr(published_db, "enabled", lambda: False)
    wt, note = site_git.ensure_worktree(tmp_path)
    assert wt is None and "DATABASE_URL" in note


def test_radar_menu_goes_to_the_database_in_db_mode_and_not_to_git(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_SITE_PUBLISH_VIA", "db")
    monkeypatch.setattr(published_db, "enabled", lambda: True)
    monkeypatch.setattr(site_git, "_git", lambda *a, **k: (_ for _ in ()).throw(AssertionError("git ran")))
    monkeypatch.setattr(site_git, "repo_root", lambda start=None: tmp_path)
    sent: dict = {}
    monkeypatch.setattr(published_db, "publish_documents", lambda docs, **k: sent.update(docs) or {"db": True})
    portfolio = {"generated_at": "2026-10-01T10:00:00+00:00", "vectors": [{"title": "T", "thesis": "x", "sources": ["https://a.example/1"]}]}
    out = radar_page.publish_menu(portfolio)
    assert out["published"] is True and list(sent) == ["radar/2026-10-01-1000.json"]
    assert sent["radar/2026-10-01-1000.json"]["leads"][0]["title"] == "T"


def test_radar_menu_reports_failure_when_the_db_write_fails_in_db_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_SITE_PUBLISH_VIA", "db")
    monkeypatch.setattr(published_db, "enabled", lambda: True)
    monkeypatch.setattr(site_git, "repo_root", lambda start=None: tmp_path)
    monkeypatch.setattr(published_db, "publish_documents", lambda docs, **k: {"db": False, "note": "boom"})
    out = radar_page.publish_menu({"generated_at": "2026-10-01T10:00:00+00:00", "vectors": [{"title": "T", "thesis": "x"}]})
    assert out["published"] is False and "boom" in out["note"]


def test_backfill_maps_site_files_to_document_paths(monkeypatch, tmp_path) -> None:
    for rel, body in {"content/intel/daily/geopolitics/2026-10-01.json": {"a": 1},
                      "content/radar/2026-10-01-1000.json": {"r": 1},
                      "public/data/index.json": {"i": 1}, "public/data/articles/s.json": {"t": 1}}.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(body), encoding="utf-8")
    (tmp_path / "content" / "articles").mkdir(parents=True)
    seen: dict = {}
    monkeypatch.setattr(published_db, "publish_documents", lambda docs, **k: seen.update(docs) or {"db": True})
    published_db.backfill(tmp_path)
    assert set(seen) == {"daily/geopolitics/2026-10-01.json", "radar/2026-10-01-1000.json",
                         "data/index.json", "data/articles/s.json"}
