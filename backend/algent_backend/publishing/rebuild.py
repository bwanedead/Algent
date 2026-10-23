"""
``newsroom publish rebuild-all`` - republish everything the site reads from the server's local stores (docs/architecture/published-content.md).

The cut-over to the object store (and the recovery after any bucket loss) is one command. Every step builds its documents from a local
store - the system of record - and hands them to the one document path, so the run is IDEMPOTENT: a document whose content hash is already
in the local manifest is skipped, a re-run after a failure sends only what is missing, and nothing is read back from the bucket.

    steps (in order)   what it builds from
    site-documents     the desk's JSON the publishers staged: content/intel (dailies, dossiers, actors, snapshots, briefs, record), content/radar,
                       public/data (the agent feeds, article twins)
    articles           content/articles/*.md -> articles/<slug>.json + articles/index.json
    images             public/analytics/** (article images) -> analytics/**
    live               live events / stats / anomalies documents and the basemap
    maritime           maritime/live|recent|counts|vessel documents (maritime_store/events.json)
    sanctions          sanctions/recent + per-country (sanctions_store)
    calendar           calendar/next (calendar_store)
    geoledger          geo/c|a|events|events-assets|countries documents and the grid rollups (geoledger_store)
    markets            data/track-record.json     ai-benchmarks   data/ai-benchmarks.json
    satellite          chips + live/satellite.json from the satellite store

``--dry-run`` builds every document and reports how many WOULD be sent and their gzipped size (an estimate of the Class A operations the run
costs), sending and recording nothing. A run is bounded by the free-tier guard (object_budget.py): past the hard stop it stops and says so.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import asset_store, object_docs, site_data, site_git


def _json_tree(folder: Path, prefix: str) -> dict[str, Any]:
    """Every ``*.json`` under ``folder`` as ``{prefix + relative path: parsed}`` (unreadable files are skipped)."""
    out: dict[str, Any] = {}
    for p in sorted(folder.rglob("*.json")) if folder.is_dir() else []:
        try:
            out[prefix + p.relative_to(folder).as_posix()] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def site_roots(root: Path | None = None) -> list[Path]:
    """Where the staged site content lives: the publish worktree first (it is what was last published), then the repo's own site folder."""
    root = root or site_git.repo_root()
    return [p for p in (site_git.live_site_dir(root), site_git.site_dir(root)) if p.is_dir()]


def site_documents(roots: list[Path]) -> dict[str, Any]:
    docs: dict[str, Any] = {}
    for site in reversed(roots):                      # the repo copy first, so the worktree (newer) overrides it
        docs.update({**_json_tree(site / "content" / "intel", ""), **_json_tree(site / "content" / "radar", "radar/"),
                     **_json_tree(site / "public" / "data", "data/")})
    return docs


def article_items(roots: list[Path]) -> list[tuple[str, str, str, str]]:
    import re

    found: dict[str, str] = {}
    for site in reversed(roots):
        for md in sorted((site / "content" / "articles").glob("*.md")):
            found[md.stem] = md.read_text(encoding="utf-8")
    out = []
    for slug, text in sorted(found.items()):
        title = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
        status = re.search(r"^status:\s*(\S+)", text, re.MULTILINE)
        out.append((slug, text, title.group(1).strip("'\" ") if title else "", status.group(1) if status else ""))
    return out


def _docs_step(build: Callable[[], dict[str, Any]], dry_run: bool, http: Any, keep: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    docs = build()
    if keep is not None:
        docs = keep(docs)
    if dry_run:
        return object_docs.dry_run_report(docs)
    return site_data.publish(docs, http=http)


def run(*, dry_run: bool = False, only: list[str] | None = None, roots: list[Path] | None = None, http: Any = None,
        keep: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Run every step (or just ``only``). Returns one result per step; never raises (a step that fails is reported, the rest still run).
    ``keep`` narrows each step's documents before they are sent (``staging_docs.sample``: the staging channel copies a sample, not everything)."""
    roots = roots if roots is not None else site_roots()
    out: dict[str, Any] = {"dry_run": dry_run, "roots": [str(r) for r in roots], "steps": {}}

    def step(name: str, fn: Callable[[], dict[str, Any]]) -> None:
        if only and name not in only:
            return
        try:
            out["steps"][name] = fn()
        except Exception as exc:  # noqa: BLE001 - one broken store must not stop the others
            out["steps"][name] = {"ok": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}

    step("site-documents", lambda: _docs_step(lambda: site_documents(roots), dry_run, http, keep))
    step("articles", lambda: object_docs.publish_articles(article_items(roots), http=http, dry_run=dry_run))

    def images() -> dict[str, Any]:
        files: dict[str, bytes] = {}
        for site in reversed(roots):
            base = site / "public"
            files.update({"/" + p.relative_to(base).as_posix(): p.read_bytes() for p in sorted((base / "analytics").rglob("*")) if p.is_file()})
        if dry_run:
            return {"ok": True, "dry_run": True, "files": len(files), "bytes": sum(len(b) for b in files.values()),
                    "note": "uploaded unless its content hash is already in asset_hashes.json"}
        return asset_store.upload(files, http=http)

    step("images", images)

    def live() -> dict[str, Any]:
        from algent_backend.live import publish as live_publish
        from algent_backend.live.memory import anomalies

        docs = live_publish.documents()
        docs.update(anomalies.documents(anomalies.read_current()))
        res = _docs_step(lambda: docs, dry_run, http, keep)
        if not dry_run:
            res["world"] = live_publish.publish_world(force=True)
        return res

    step("live", live)
    def maritime() -> dict[str, Any]:
        from algent_backend.maritime import publish as maritime_publish

        return _docs_step(maritime_publish.documents, dry_run, http, keep)

    def sanctions() -> dict[str, Any]:
        from algent_backend.sanctions import publish as sanctions_publish

        return _docs_step(sanctions_publish.documents, dry_run, http, keep)

    def calendar() -> dict[str, Any]:
        from algent_backend.lookahead import publish as calendar_publish

        return _docs_step(calendar_publish.documents, dry_run, http, keep)

    step("maritime", maritime)
    step("sanctions", sanctions)
    step("calendar", calendar)

    def geo() -> dict[str, Any]:
        from algent_backend.geoledger import grid, site_docs
        from algent_backend.geoledger.store import Ledger

        ledger = Ledger()
        docs = site_docs.documents(ledger)
        res = _docs_step(lambda: docs, dry_run, http, keep)
        if not dry_run and keep is None:                       # the grid rollups are published whole: a sampled (staging) run leaves them to site_docs' own grid documents
            res["grid"] = grid.publish_rollups(ledger)
        return res

    step("geoledger", geo)

    def markets() -> dict[str, Any]:
        from algent_backend.markets import publish as markets_publish
        from algent_backend.markets import score

        return _docs_step(lambda: {markets_publish.PATH: score.track_record()}, dry_run, http, keep)

    def ai_benchmarks() -> dict[str, Any]:
        from algent_backend.ai_benchmarks import publish as ai_publish

        return _docs_step(lambda: {ai_publish.PATH: ai_publish.document()}, dry_run, http, keep)

    step("markets", markets)
    step("ai-benchmarks", ai_benchmarks)

    def satellite() -> dict[str, Any]:
        from algent_backend.satellite import run as satellite_run
        from algent_backend.satellite import store as satellite_store

        doc = satellite_store.read_json("doc.json", None)
        if not doc:
            return {"ok": True, "note": "no satellite document on this machine"}
        if dry_run:
            return {"ok": True, "dry_run": True, "sites": len(doc.get("sites", []))}
        return satellite_run.publish(doc, http=http)

    step("satellite", satellite)
    out["ok"] = all(s.get("ok", True) is not False and s.get("db", True) is not False for s in out["steps"].values())
    if not dry_run:
        out["note"] = "set NEXT_PUBLIC_DATA_BASE in Vercel to the bucket's public URL, then deploy (docs/architecture/database-budget.md runbook)"
    return out


__all__ = ["run", "site_documents", "article_items", "site_roots"]
