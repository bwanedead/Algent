"""Publish-to-database writer (fake connection) and migration 004's exposure surface. No database needed."""

from __future__ import annotations

import gzip
import re

from algent_backend.database import available
from algent_backend.publishing import doc_store, published_db

MD = "---\ntitle: T\npublished_at: '2026-10-01T10:00:00+00:00'\n---\n\nbody\n"


class FakeCursor:
    def __init__(self, conn): self.conn = conn; self._row = None; self._rows = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=()):
        self.conn.calls.append((sql.strip().split()[0:3], params))
        if self.conn.fail:
            raise RuntimeError("boom")
        if sql.strip().startswith("select path, sha256"):
            self._rows = [(p, self.conn.hashes[p]) for p in params[0] if p in self.conn.hashes]
        self._row = (1,) if "returning" in sql and self.conn.changed else None
    def fetchone(self): return self._row
    def fetchall(self): return self._rows


class FakeConn:
    def __init__(self, changed=True, fail=False, hashes=None):
        self.calls = []; self.changed = changed; self.fail = fail; self.committed = False; self.hashes = hashes or {}
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return FakeCursor(self)
    def commit(self): self.committed = True


class FakeHttp:
    """Stands in for Storage: records every upload, answers ``status`` (per key prefix override in ``bad``)."""
    def __init__(self, status=200, bad=()): self.sent = {}; self.status = status; self.bad = bad
    def __call__(self, method, url, headers, body):
        key = url.split("/published-assets/", 1)[1]
        self.sent[key] = (headers, body)
        return 500 if any(b in key for b in self.bad) else self.status


def test_publish_article_upserts_and_appends_a_revision() -> None:
    conn = FakeConn()
    out = published_db.publish_article("s", MD, title="T", status="publishable", connect=lambda: conn)
    assert out == {"db": True, "articles": 1} and conn.committed
    assert conn.calls[0][1][3] == "2026-10-01T10:00:00+00:00"        # published_at read from frontmatter
    assert len(conn.calls) == 3                                       # upsert + revision + trim to the last few


def test_unchanged_article_writes_no_revision() -> None:
    conn = FakeConn(changed=False)
    out = published_db.publish_article("s", MD, connect=lambda: conn)
    assert out["articles"] == 0 and len(conn.calls) == 1


def _index_rows(conn):
    return {c[1][0]: c[1] for c in conn.calls if c[0][:3] == ["insert", "into", "published_intel_documents"]}


def test_documents_go_to_storage_gzipped_and_the_table_gets_only_an_index_row() -> None:
    conn, http = FakeConn(), FakeHttp()
    docs = {"daily/geopolitics/2026-10-01.json": {"a": 1, "big": "x" * 5000}, "record.json": {}}
    out = published_db.publish_documents(docs, connect=lambda: conn, http=http)
    assert out == {"db": True, "documents": 2, "of": 2, "unchanged": 0} and conn.committed
    assert set(http.sent) == {"docs/daily/geopolitics/2026-10-01.json.gz", "docs/record.json.gz"}
    headers, body = http.sent["docs/daily/geopolitics/2026-10-01.json.gz"]
    assert gzip.decompress(body) == doc_store.canonical(docs["daily/geopolitics/2026-10-01.json"]) and headers["Content-Type"] == "application/gzip"
    rows = _index_rows(conn)
    path, kind, key, size, sha = rows["daily/geopolitics/2026-10-01.json"]
    assert (kind, key) == ("daily", "docs/daily/geopolitics/2026-10-01.json.gz") and size > 5000 and len(sha) == 64
    assert rows["record.json"][1] == "record"
    assert all("body" not in str(p) or p is None for p in rows["record.json"])          # the body never travels to Postgres


def test_an_unchanged_document_is_not_uploaded_or_indexed_again() -> None:
    body = {"a": 1}
    sha = doc_store.pack("x/y.json", body).sha256
    conn, http = FakeConn(hashes={"x/y.json": sha}), FakeHttp()
    out = published_db.publish_documents({"x/y.json": body, "x/z.json": {"b": 2}}, connect=lambda: conn, http=http)
    assert out["documents"] == 1 and out["unchanged"] == 1 and list(http.sent) == ["docs/x/z.json.gz"]
    assert list(_index_rows(conn)) == ["x/z.json"]
    again = published_db.publish_documents({"x/y.json": body}, connect=lambda: FakeConn(hashes={"x/y.json": sha}), http=http)
    assert again == {"db": True, "documents": 0, "of": 1, "unchanged": 1}
    forced = published_db.publish_documents({"x/y.json": body}, connect=lambda: FakeConn(hashes={"x/y.json": sha}), http=FakeHttp(), force=True)
    assert forced["documents"] == 1                                                   # a backfill resends everything


def test_key_order_does_not_look_like_a_change() -> None:
    assert doc_store.pack("a.json", {"x": 1, "y": [1, 2]}).sha256 == doc_store.pack("a.json", {"y": [1, 2], "x": 1}).sha256


def test_a_failed_upload_writes_no_index_row_for_it_and_is_reported() -> None:
    conn, http = FakeConn(), FakeHttp(bad=("bad",))
    out = published_db.publish_documents({"ok/a.json": {"a": 1}, "bad/b.json": {"b": 1}}, connect=lambda: conn, http=http)
    assert out["db"] is False and "1 of 2 document uploads failed" in out["note"]
    assert list(_index_rows(conn)) == ["ok/a.json"] and conn.committed                 # what landed is indexed, the rest retries


def test_a_document_over_the_object_cap_is_refused_and_logged(monkeypatch, capsys) -> None:
    from algent_backend.database import flags

    monkeypatch.setattr(flags, "STORAGE_OBJECT_BYTES", 10)
    conn, http = FakeConn(), FakeHttp()
    out = published_db.publish_documents({"big.json": {"k": "v" * 500}}, connect=lambda: conn, http=http)
    assert out["documents"] == 0 and "object limit" in out["refused"][0] and not http.sent and not _index_rows(conn)
    assert "REFUSED" in capsys.readouterr().out


def test_an_article_over_the_row_cap_is_refused(monkeypatch) -> None:
    from algent_backend.database import flags

    monkeypatch.setattr(flags, "ROW_CAP_BYTES", 50)
    conn = FakeConn()
    out = published_db.publish_article("s", MD + "x" * 200, connect=lambda: conn)
    assert out["db"] is False and "row cap" in out["note"] and conn.calls == []


def test_documents_need_storage_not_just_the_database(monkeypatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    out = published_db.publish_documents({"x/y.json": {}}, connect=lambda: FakeConn())
    assert out["db"] is False and "Storage" in out["note"]


def test_errors_are_reported_never_raised() -> None:
    out = published_db.publish_documents({"x/y.json": {}}, connect=lambda: FakeConn(fail=True), http=FakeHttp())
    assert out["db"] is False and "RuntimeError" in out["note"]


def test_noop_without_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert published_db.publish_article("s", MD)["db"] is False


def test_migration_004_exposes_only_published_tables() -> None:
    sql = next(p for p in available() if p.stem == "004_published_content").read_text(encoding="utf-8")
    code = "\n".join(l.split("--")[0] for l in sql.splitlines())
    created = set(re.findall(r"create table (\w+)", code))
    assert created == {"published_articles", "published_intel_documents", "published_article_revisions"}
    assert set(re.findall(r"grant\s+select\s+on\s+(\w+)\s+to\s+anon", code)) == {"published_articles", "published_intel_documents"}
    assert len(re.findall(r"grant\b", code)) == 2                                # nothing else is granted, to anyone
    assert set(re.findall(r"create policy \w+ on (\w+)\s+for select to anon", code)) == {"published_articles", "published_intel_documents"}
    assert len(re.findall(r"create policy", code)) == 2
    assert len(re.findall(r"enable row level security", code)) == len(created)  # RLS on every table, revisions included
    assert "using (visible)" in code


def test_migration_014_makes_the_body_optional_and_adds_the_index_fields() -> None:
    sql = next(p for p in available() if p.stem == "014_documents_in_storage").read_text(encoding="utf-8")
    code = "\n".join(l.split("--")[0] for l in sql.splitlines())
    assert "alter column body drop not null" in code
    for col in ("storage_key", "size_bytes", "sha256"):
        assert f"add column if not exists {col}" in code
    assert "grant" not in code and "policy" not in code                      # exposure is unchanged: the columns are as public as the rows
