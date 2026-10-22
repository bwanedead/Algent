"""
Documents in the object store, no database - how the site's JSON reaches it (docs/architecture/published-content.md).

``publish(docs)`` takes ``{document path: body}`` (``daily/geopolitics/2026-10-01.json``, ``record.json``, ``live/events.json`` ...), packs each as
canonical JSON, gzips it and puts it at ``docs/<path>.gz`` (``doc_store`` fixes the naming and caps). What "changed" means is decided from a
LOCAL hash manifest (``backend/publish_held/doc_hashes.json``) - the server never reads the bucket back for what it already holds - so an
unchanged document costs no request at all.

The site cannot list a bucket, so the writer also keeps tiny **name indexes**: ``docs/_names/<dir>.json`` is the sorted list of document names
directly inside ``<dir>`` (``["2026-10-01.json", ...]``), rewritten only when a directory gains a document. ``intelNames`` reads those.

Articles are documents too: ``articles/<slug>.json`` (the markdown) and ``articles/index.json`` (every article's front matter, no body) so the
list pages fetch one small file and a reader fetches one article.

Contract (same as ``published_db``): never raises; the result carries ``db``/``ok`` True only when everything that had to land did.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from algent_backend.database import flags as budget

from . import asset_store, doc_store, object_store

NAMES_DIR = "_names"
_LOCK = threading.RLock()


def manifest_path() -> Path:

    return object_store.held_dir() / "doc_hashes.json"


def _load(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict[str, str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=0, sort_keys=True), encoding="utf-8")
    except OSError:
        pass   # an optimisation: losing it costs one re-upload round


def names_path(directory: str) -> str:
    return f"{NAMES_DIR}/{directory}.json"


def _names_in(paths: set[str], directory: str) -> list[str]:
    cut = len(directory) + 1
    return sorted(p[cut:] for p in paths if p.startswith(directory + "/") and "/" not in p[cut:])


def _dirs_of(path: str) -> list[str]:
    """Every ancestor directory of a document path, deepest first (``a/b/c.json`` -> ``["a/b", "a"]``)."""
    parts = path.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(len(parts), 0, -1)]


def publish(docs: dict[str, Any], *, http: Any = None, force: bool = False, manifest: Path | None = None,
            names: bool = True) -> dict[str, Any]:
    """Store documents in the object store. Skips unchanged ones (local manifest), refuses over-cap ones, then refreshes the name
    indexes of directories that gained a document. Never raises."""
    store = asset_store._store_for(http)  # noqa: SLF001 - same package, one place decides the backend
    if store is None:
        return {"db": False, "ok": False, "note": "document storage off (no object store configured: set the R2_* names, docs/credentials.md)"}
    try:
        mpath = manifest or manifest_path()
        with _LOCK:
            state = _load(mpath)
            ident = store.ident
            packed = [doc_store.pack(path, body) for path, body in sorted(docs.items())]
            changed = [p for p in packed if force or state.get(f"{ident}|{p.path}") != p.sha256]
            refused, todo = [], []
            for p in changed:                  # the size cap needs the gzip, which only a changed document ever pays for
                if (why := doc_store.over_cap(p)):
                    print(f"[object_docs] REFUSED {why}", flush=True)
                    refused.append(why)
                else:
                    todo.append(p)
            out: dict[str, Any] = {"documents": 0, "of": len(docs), "unchanged": len(packed) - len(changed)}
            if refused:
                out["refused"] = refused
            failed: set[str] = set()
            if todo:
                res = asset_store.upload({p.site_path: p.gz for p in todo}, http=http, force=True, cache_control=doc_store.CACHE_CONTROL,
                                         workers=budget.UPLOAD_WORKERS)
                failed = {f.split(" (", 1)[0] for f in res["failed"]}
                if failed and not all(f.startswith("/" + doc_store.PREFIX) for f in failed):
                    failed = {p.site_path for p in todo}          # a whole-call failure: nothing is known to have landed
            sent = [p for p in todo if p.site_path not in failed]
            had = {k.split("|", 1)[1] for k in state if k.startswith(ident + "|")}
            for p in sent:
                state[f"{ident}|{p.path}"] = p.sha256
            out["documents"] = len(sent)
            _save(mpath, state)
            if names and sent:
                paths = {k.split("|", 1)[1] for k in state if k.startswith(ident + "|")}
                dirs = {d for p in sent if p.path not in had for d in _dirs_of(p.path)} if not force else {d for p in sent for d in _dirs_of(p.path)}
                if dirs:
                    idx = {names_path(d): _names_in(paths, d) for d in sorted(dirs)}
                    res2 = publish(idx, http=http, force=False, manifest=mpath, names=False)
                    if not res2.get("ok"):
                        failed.add("names index")
        out["ok"] = out["db"] = not failed
        if failed:
            out["note"] = f"{len(failed)} document upload(s) failed: {sorted(failed)[:3]}"
        return out
    except Exception as exc:  # noqa: BLE001 - the local stores are the record; publishing is an addition
        return {"db": False, "ok": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}


# ── articles ──────────────────────────────────────────────────────────────────────────────────────

def _front_matter(markdown: str) -> dict[str, Any]:
    import yaml

    if not markdown.startswith("---"):
        return {}
    head = markdown[3:].split("\n---", 1)[0]
    try:
        data = yaml.safe_load(head)
    except yaml.YAMLError:
        return {}
    return json.loads(json.dumps(data, default=str)) if isinstance(data, dict) else {}


def articles_index_path() -> Path:

    return object_store.held_dir() / "articles_index.json"


def _index_doc(entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(entries.values(), key=lambda e: str(e.get("published_at") or e.get("data", {}).get("date") or ""), reverse=True)
    return {"articles": rows}


def publish_article(slug: str, markdown: str, *, title: str = "", status: str = "", http: Any = None,
                    index_file: Path | None = None, manifest: Path | None = None) -> dict[str, Any]:
    """An article is ``articles/<slug>.json`` (its markdown) plus a refreshed ``articles/index.json`` (front matter of all, no bodies)."""
    markdown = markdown.replace(chr(0), "")
    if (why := doc_store.row_over_cap(f"article {slug}", markdown)):
        print(f"[object_docs] REFUSED {why}", flush=True)
        return {"db": False, "ok": False, "note": why}
    data = _front_matter(markdown)
    published_at = str(data.get("published_at") or "")
    ipath = index_file or articles_index_path()
    with _LOCK:
        entries = _load_entries(ipath)
        entries[slug] = {"slug": slug, "title": title or str(data.get("title") or slug), "status": status or str(data.get("status") or ""),
                         "published_at": published_at, "data": data}
        _save_entries(ipath, entries)
    res = publish({f"articles/{slug}.json": {"slug": slug, "title": entries[slug]["title"], "status": entries[slug]["status"],
                                             "published_at": published_at, "markdown": markdown},
                   "articles/index.json": _index_doc(entries)}, http=http, manifest=manifest)
    res["articles"] = 1 if res.get("documents") else 0
    return res


def _load_entries(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_entries(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    except OSError:
        pass
