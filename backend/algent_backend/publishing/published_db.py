"""
Publish-to-database — the live path to the site (docs/architecture/published-content.md).

The publishers still write files (TRANSITIONAL: the files are the site's fallback reader; with
``flags.SITE_PUBLISH_VIA = "git"`` the `site-live` commit still ships them, with ``"db"`` there is no commit and
the rows + Storage assets are the whole publish; retire the file path after the cut-over week). Alongside them, this module upserts the
same content into ``published_articles`` / ``published_intel_documents`` so the site shows it within
its revalidation window with no redeploy.

Documents (``publish_documents``) are NOT stored in Postgres: the body is a gzipped object in the public Storage bucket and the table keeps
only an index row (``doc_store.py``, docs/architecture/database-budget.md), so a rewrite costs the 500 MB free-plan database nothing. Articles
stay in Postgres (small, relational) behind a per-row size cap.

Contract: never raises into a run (errors come back in the result like the other publishers);
idempotent (an unchanged row is not rewritten); a no-op without ``DATABASE_URL`` or with
``ALGENT_DB_PUBLISH=0``. The environment only — ``.env`` is NOT loaded here, so a test run on a dev
machine can never reach the live database by accident.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from algent_backend.database import flags as budget

from . import asset_store, doc_store

_OFF = ("0", "false", "no", "off")
_FM_DATE = re.compile(r"^published_at:\s*['\"]?([^'\"\n]+)", re.MULTILINE)

_ARTICLE = """
insert into published_articles (slug, title, status, published_at, markdown)
values (%s, %s, %s, %s, %s)
on conflict (slug) do update
   set title = excluded.title, status = excluded.status, published_at = excluded.published_at,
       markdown = excluded.markdown, visible = true, updated_at = now()
 where published_articles.markdown is distinct from excluded.markdown
returning 1
"""
_REVISION = "insert into published_article_revisions (slug, markdown) values (%s, %s)"
_REVISIONS_TRIM = """
delete from published_article_revisions
 where slug = %s and id not in (select id from published_article_revisions where slug = %s order by id desc limit %s)
"""
_HASHES = "select path, sha256 from published_intel_documents where path = any(%s)"
_INDEX = """
insert into published_intel_documents (path, kind, body, storage_key, size_bytes, sha256)
values (%s, %s, null, %s, %s, %s)
on conflict (path) do update
   set body = null, storage_key = excluded.storage_key, size_bytes = excluded.size_bytes, sha256 = excluded.sha256,
       visible = true, updated_at = now()
"""


def enabled() -> bool:
    return bool(os.environ.get("DATABASE_URL")) and os.environ.get("ALGENT_DB_PUBLISH", "1").strip().lower() not in _OFF


def _connect():
    import psycopg   # only a real connection needs the driver

    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _run(work: Callable[[Any], dict], connect: Callable[[], Any] | None) -> dict[str, Any]:
    if connect is None and not enabled():
        return {"db": False, "note": "database publishing off (no DATABASE_URL)"}
    try:
        with (connect or _connect)() as conn:
            result = work(conn)
            conn.commit()
        return {"db": True, **result}
    except Exception as exc:  # noqa: BLE001 — the files are already written; the run goes on
        return {"db": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _published_at(markdown: str) -> str | None:
    if not markdown.startswith("---"):
        return None
    m = _FM_DATE.search(markdown.split("\n---", 1)[0])
    return m.group(1).strip() if m else None


#: Postgres text and jsonb reject NUL (0x00); it carries no meaning in published text, so it is dropped at this edge.
NUL_ESCAPE = "\\u0000"


def _no_nul(text: str) -> str:
    return (text or "").replace(chr(0), "")


def publish_article(slug: str, markdown: str, *, title: str = "", status: str = "",
                    connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Upsert one article (its full site markdown). A changed body also appends a revision."""
    markdown = _no_nul(markdown)          # Postgres text rejects NUL; scraped source text sometimes carries it
    title = _no_nul(title)
    if (why := doc_store.row_over_cap(f"article {slug}", markdown)):
        print(f"[published_db] REFUSED {why}", flush=True)
        return {"db": False, "note": why}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.execute(_ARTICLE, (slug, title or slug, status, _published_at(markdown), markdown))
            changed = cur.fetchone() is not None
            if changed:
                cur.execute(_REVISION, (slug, markdown))
                cur.execute(_REVISIONS_TRIM, (slug, slug, budget.REVISIONS_KEEP))     # bounded history (database-budget.md)
        return {"articles": 1 if changed else 0}

    return _run(work, connect)


def publish_documents(docs: dict[str, dict], *, connect: Callable[[], Any] | None = None, http: Callable[..., int] | None = None,
                      force: bool = False) -> dict[str, Any]:
    """Store desk JSON documents keyed by their path under the intel directory (``daily/geopolitics/…json``).

    Each body goes to Storage as ``docs/<path>.gz`` and the table gets an index row. A document whose hash already matches its index row
    is skipped without any write (``force`` resends everything); one over the object cap is refused and logged. Storage is written BEFORE
    the index row, so a listing never names a missing object, and a failed upload leaves its old row untouched (the rest still land, then
    the call reports the failure so db-mode publishes do not read as success)."""
    if connect is None and not enabled():
        return {"db": False, "note": "database publishing off (no DATABASE_URL)"}
    if http is None and not asset_store.enabled():
        return {"db": False, "note": "document storage off (set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY: documents live in Storage, not Postgres)"}

    def work(conn: Any) -> dict:
        packed = [doc_store.pack(path, body) for path, body in sorted(docs.items())]
        known: dict[str, str] = {}
        if packed and not force:
            with conn.cursor() as cur:
                cur.execute(_HASHES, ([p.path for p in packed],))
                known = {row[0]: row[1] for row in cur.fetchall()}
        changed = [p for p in packed if known.get(p.path) != p.sha256]
        refused = []
        todo = []
        for p in changed:                  # the size cap needs the gzip, which only a changed document ever pays for
            if (why := doc_store.over_cap(p)):
                print(f"[published_db] REFUSED {why}", flush=True)
                refused.append(why)
            else:
                todo.append(p)
        out: dict[str, Any] = {"documents": 0, "of": len(docs), "unchanged": len(packed) - len(changed)}
        if refused:
            out["refused"] = refused
        if not todo:
            return out
        res = asset_store.upload({p.site_path: p.gz for p in todo}, http=http, force=True, cache_control=doc_store.CACHE_CONTROL,
                                 workers=budget.UPLOAD_WORKERS)
        failed = {f.split(" (", 1)[0] for f in res["failed"]}
        if failed and not all(f.startswith("/" + doc_store.PREFIX) for f in failed):
            failed = {p.site_path for p in todo}              # a whole-call failure: nothing is known to have landed
        sent = [p for p in todo if p.site_path not in failed]
        with conn.cursor() as cur:
            for p in sent:
                cur.execute(_INDEX, (p.path, p.kind, p.key, p.size_bytes, p.sha256))
        out["documents"] = len(sent)
        if failed:
            conn.commit()                                    # keep the index rows of what did land, then report the rest
            raise RuntimeError(f"{len(failed)} of {len(todo)} document uploads failed: {sorted(failed)[:3]}")
        return out

    return _run(work, connect)


def _json_tree(folder, prefix: str) -> dict[str, dict]:
    """Every ``*.json`` under ``folder`` as ``{prefix + relative path: parsed}`` (unreadable files are skipped)."""
    out: dict[str, dict] = {}
    for p in sorted(folder.rglob("*.json")) if folder.is_dir() else []:
        try:
            out[prefix + p.relative_to(folder).as_posix()] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def backfill(site_dir) -> dict[str, Any]:
    """One-off: push the site's existing content files into the tables. Document paths: desk files keep their path
    under ``content/intel`` (``daily/…``), radar editions are ``radar/<slug>.json``, and the agent feeds under
    ``public/data`` are ``data/<rel>`` (``data/index.json``, ``data/articles/<slug>.json``, …)."""
    from pathlib import Path

    site = Path(site_dir)
    docs = {**_json_tree(site / "content" / "intel", ""), **_json_tree(site / "content" / "radar", "radar/"),
            **_json_tree(site / "public" / "data", "data/")}
    out: dict[str, Any] = {"documents": publish_documents(docs, force=True)}
    for md in sorted((site / "content" / "articles").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        title = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
        status = re.search(r"^status:\s*(\S+)", text, re.MULTILINE)
        out[md.stem] = publish_article(md.stem, text, title=title.group(1).strip("'\" ") if title else "",
                                       status=status.group(1) if status else "")
    return out


if __name__ == "__main__":   # python -m algent_backend.publishing.published_db <site dir>
    import sys

    print(json.dumps(backfill(sys.argv[1]), indent=2))
