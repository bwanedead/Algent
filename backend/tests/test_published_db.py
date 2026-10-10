"""Publish-to-database writer (fake connection) and migration 004's exposure surface. No database needed."""

from __future__ import annotations

import re

from algent_backend.database import available
from algent_backend.publishing import published_db

MD = "---\ntitle: T\npublished_at: '2026-10-01T10:00:00+00:00'\n---\n\nbody\n"


class FakeCursor:
    def __init__(self, conn): self.conn = conn; self._row = None
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=()):
        self.conn.calls.append((sql.strip().split()[0:3], params))
        if self.conn.fail:
            raise RuntimeError("boom")
        self._row = (1,) if "returning" in sql and self.conn.changed else None
    def fetchone(self): return self._row


class FakeConn:
    def __init__(self, changed=True, fail=False): self.calls = []; self.changed = changed; self.fail = fail; self.committed = False
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return FakeCursor(self)
    def commit(self): self.committed = True


def test_publish_article_upserts_and_appends_a_revision() -> None:
    conn = FakeConn()
    out = published_db.publish_article("s", MD, title="T", status="publishable", connect=lambda: conn)
    assert out == {"db": True, "articles": 1} and conn.committed
    assert conn.calls[0][1][3] == "2026-10-01T10:00:00+00:00"        # published_at read from frontmatter
    assert len(conn.calls) == 2                                       # upsert + revision


def test_unchanged_article_writes_no_revision() -> None:
    conn = FakeConn(changed=False)
    out = published_db.publish_article("s", MD, connect=lambda: conn)
    assert out["articles"] == 0 and len(conn.calls) == 1


def test_publish_documents_keys_by_path_and_kind() -> None:
    conn = FakeConn()
    out = published_db.publish_documents({"daily/geopolitics/2026-10-01.json": {"a": 1}, "record.json": {}},
                                         connect=lambda: conn)
    assert out == {"db": True, "documents": 2, "of": 2}
    kinds = {c[1][0]: c[1][1] for c in conn.calls}
    assert kinds == {"daily/geopolitics/2026-10-01.json": "daily", "record.json": "record"}


def test_errors_are_reported_never_raised() -> None:
    out = published_db.publish_documents({"x/y.json": {}}, connect=lambda: FakeConn(fail=True))
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
