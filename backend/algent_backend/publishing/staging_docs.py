"""
``newsroom publish stage-from-prod`` - copy a SAMPLE of what production publishes into the staging channel, so a preview deployment can render every
kind of page (docs/guides/deploy.md). It is the first step of the deploy routine: stage the current data, check the preview, then promote.

Everything comes from the server's LOCAL stores - the staged site documents, the domain publishers' own builders (``rebuild``) and the views store -
and nothing is read back from the bucket. It goes through the one document path under ``ALGENT_PUBLISH_TARGET=staging``, so it is hash-skipped against
the staging manifest (an unchanged document costs no request), metered by the shared R2 guard and held to the staging allowance (``staging.Ledger``).

The sample (``database/flags.py``): per directory the newest N documents (``STAGING_DIR_CAPS``), per view family the N largest (``STAGING_VIEW_CAPS``),
every index and ``latest`` document, and every small family whole. Article images and satellite chips are not staged (the bulk of the bytes); a preview
shows those as missing unless ``--only images`` is asked for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from algent_backend.database import flags as budget

from . import object_docs, rebuild, staging

#: Rebuild steps a sample covers by default (``rebuild.run`` step names). Images and satellite are opt-in.
DEFAULT_STEPS = ("site-documents", "articles", "live", "maritime", "sanctions", "calendar", "geoledger", "markets", "ai-benchmarks")
_ALWAYS = ("index", "latest")


def _parent(path: str) -> str:
    return path.rpartition("/")[0]


def sample(docs: dict[str, Any]) -> dict[str, Any]:
    """The documents of a step a preview needs: per directory in ``STAGING_DIR_CAPS`` the newest N names, plus every index/latest; the rest whole."""
    by_dir: dict[str, list[str]] = {}
    for path in docs:
        by_dir.setdefault(_parent(path), []).append(path)
    keep: set[str] = set()
    for directory, paths in by_dir.items():
        cap = next((n for pre, n in budget.STAGING_DIR_CAPS if (directory + "/").startswith(pre if pre.endswith("/") else pre + "/")), None)
        if cap is None:
            keep.update(paths)
            continue
        always = [p for p in paths if p.rpartition("/")[2].removesuffix(".json").startswith(_ALWAYS)]
        keep.update(always)
        keep.update(sorted((p for p in paths if p not in always), reverse=True)[:cap])
    return {p: docs[p] for p in docs if p in keep}


def view_documents(root: Path) -> dict[str, Any]:
    """``{views/<key>.json: body}`` for the sample of the production views store at ``root``: per family in ``STAGING_VIEW_CAPS`` the N largest."""
    from algent_backend.views import flags as view_flags
    from algent_backend.views.publish import STATE_FILE

    found: list[tuple[str, str, int, Path]] = []
    for f in sorted(root.rglob("*.json")) if root.is_dir() else []:
        rel = f.relative_to(root).as_posix()
        if rel == STATE_FILE:
            continue
        family = rel.split("/", 1)[0] if "/" in rel else rel.removesuffix(".json")
        found.append((family, rel.removesuffix(".json"), f.stat().st_size, f))
    chosen: list[tuple[str, Path]] = []
    for family in sorted({fam for fam, *_ in found}):
        rows = sorted((r for r in found if r[0] == family), key=lambda r: (-r[2], r[1]))
        cap = budget.STAGING_VIEW_CAPS.get(family)
        chosen += [(key, f) for _, key, _, f in (rows if cap is None else rows[:cap])]
    out: dict[str, Any] = {}
    for key, f in chosen:
        try:
            out[f"{view_flags.PREFIX}/{key}.json"] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def stage_from_prod(*, dry_run: bool = False, only: list[str] | None = None, http: Any = None, roots: list[Path] | None = None,
                    views_root: Path | None = None) -> dict[str, Any]:
    """Publish the sample to staging. ``only`` names rebuild steps (default ``DEFAULT_STEPS``) and may include ``views``. Never raises."""
    from algent_backend.views import publish as view_publish

    steps = list(only) if only else [*DEFAULT_STEPS, "views"]
    out: dict[str, Any] = {"target": staging.STAGING, "dry_run": dry_run, "steps": {}}
    with staging.using(staging.STAGING):
        rebuild_steps = [s for s in steps if s != "views"]
        if rebuild_steps:
            rep = rebuild.run(dry_run=dry_run, only=rebuild_steps, roots=roots, http=http, keep=sample)
            out["steps"].update(rep["steps"])
        if "views" in steps:
            try:
                docs = view_documents(views_root or view_publish.store_dir(staging.PRODUCTION))
                out["steps"]["views"] = ({**object_docs.dry_run_report(docs), "views": len(docs)} if dry_run
                                         else {**object_docs.publish(docs, http=http, names=False), "views": len(docs)})
            except Exception as exc:  # noqa: BLE001 - one step failing must not stop the others
                out["steps"]["views"] = {"ok": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
        out["ledger"] = staging.ledger().status()
    out["ok"] = all(s.get("ok", True) is not False and s.get("db", True) is not False for s in out["steps"].values())
    return out
