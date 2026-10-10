"""
Publish-to-database — the live path to the site (docs/architecture/published-content.md).

The publishers still write files (TRANSITIONAL: the files are the site's fallback reader and the
`site-live` commit is how assets ship; retire the file path once the site has read Supabase in
production for a full week and assets live in object storage). Alongside them, this module upserts the
same content into ``published_articles`` / ``published_intel_documents`` so the site shows it within
its revalidation window with no redeploy.

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
_DOCUMENT = """
insert into published_intel_documents (path, kind, body)
values (%s, %s, %s::jsonb)
on conflict (path) do update
   set body = excluded.body, visible = true, updated_at = now()
 where published_intel_documents.body is distinct from excluded.body
returning 1
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

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.execute(_ARTICLE, (slug, title or slug, status, _published_at(markdown), markdown))
            changed = cur.fetchone() is not None
            if changed:
                cur.execute(_REVISION, (slug, markdown))
        return {"articles": 1 if changed else 0}

    return _run(work, connect)


def publish_documents(docs: dict[str, dict], *, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Upsert desk JSON documents keyed by their path under the intel directory (``daily/geopolitics/…json``)."""
    def work(conn: Any) -> dict:
        changed = 0
        with conn.cursor() as cur:
            for path, body in sorted(docs.items()):
                cur.execute(_DOCUMENT, (path, path.split("/", 1)[0].removesuffix(".json"),
                                        json.dumps(body, ensure_ascii=False).replace(NUL_ESCAPE, "")))
                changed += cur.fetchone() is not None
        return {"documents": changed, "of": len(docs)}

    return _run(work, connect)


def backfill(site_dir) -> dict[str, Any]:
    """One-off: push the site's existing content files (articles + intel JSON) into the tables."""
    from pathlib import Path

    site = Path(site_dir)
    intel = site / "content" / "intel"
    docs = {p.relative_to(intel).as_posix(): json.loads(p.read_text(encoding="utf-8")) for p in sorted(intel.rglob("*.json"))}
    out: dict[str, Any] = {"documents": publish_documents(docs)}
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
