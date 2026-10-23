"""
The daily's visuals, local first: every file a visual publishes is written under ``intel_store/visuals/<domain>/<date>/`` BEFORE it is uploaded.

Why: in October the visuals went only to a hosted bucket; when the bucket was dropped, 42 charts (10-14 to 10-21) existed nowhere else. The
server is the record, the bucket is the publication (docs/architecture/foundation.md). ``local_first`` wraps whatever uploader a producer is
given, so no producer (chart harness, ``scene3d``, ``native_forms``) can publish without a server copy; if the local write fails nothing is
uploaded. The store is part of ``intel_store``, so the nightly snapshot backs it up.

``republish`` is the free repair behind ``intel daily --date D --rerender``: it re-uploads the saved files of a record's visuals, and for the
native forms rebuilds the SVG still from the saved spec with no model call (so a renderer improvement reaches old days). What it cannot do: a
visual whose spec was never saved (everything published before this module existed) has nothing to rebuild from; it is reported by name and
needs the planning + structured-model calls again (``intel daily --date D --visuals-only --fresh``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .brief import safe_name
from .heat import store_dir

#: ``/analytics/daily/<domain>/<date>/<file>``: the site path every visual file is published at (``visuals.SITE_DIR``).
_SITE = re.compile(r"^/?analytics/daily/([^/]+)/(\d{4}-\d{2}-\d{2})/([^/]+)$")
Upload = Callable[[dict[str, bytes]], dict]


def day_dir(domain: str, as_of: str) -> Path:
    return store_dir() / "visuals" / safe_name(domain) / as_of


def _split(site_path: str) -> tuple[str, str, str]:
    m = _SITE.match(site_path)
    if not m:
        raise ValueError(f"not a daily visual path: {site_path}")
    return m.group(1), m.group(2), m.group(3)


def persist(files: dict[str, bytes]) -> None:
    """Write ``{site path: bytes}`` under the visuals store (atomically per file). Raises on a path that is not a daily visual or a disk error."""
    for site_path, data in files.items():
        domain, as_of, name = _split(site_path)
        target = day_dir(domain, as_of) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)


def local_first(upload: Upload) -> Upload:
    """``upload`` that writes every file to the visuals store first and uploads nothing when that write fails."""
    def wrapped(files: dict[str, bytes]) -> dict:
        try:
            persist(files)
        except (OSError, ValueError) as exc:
            return {"assets": 0, "skipped": 0, "failed": sorted(files), "ok": False, "note": f"local write failed, nothing published: {exc}"}
        return upload(files)
    return wrapped


def load(domain: str, as_of: str) -> dict[str, bytes]:
    """The saved files of one day as ``{site path: bytes}`` (empty when nothing was saved)."""
    root = day_dir(domain, as_of)
    return {f"/analytics/daily/{domain}/{as_of}/{p.name}": p.read_bytes() for p in sorted(root.iterdir()) if p.is_file() and p.suffix != ".tmp"} if root.is_dir() else {}


# ── republish ────────────────────────────────────────────────────────────────────────────────────
def _paths(visual: dict) -> list[str]:
    return [p for p in dict.fromkeys(visual.get(k) for k in ("asset", "raster", "spec", "scene", "preview")) if p and p.startswith("/analytics/daily/")]


def _still(visual: dict, saved: dict[str, bytes]) -> tuple[str, bytes] | None:
    """A rebuilt still for a native form or a scene, from its saved spec (no model); ``None`` when there is no spec or no renderer for it."""
    from . import native_forms

    kind, spec_path = visual.get("kind", ""), visual.get("spec") or visual.get("scene") or ""
    if spec_path not in saved:
        return None
    spec = json.loads(saved[spec_path])
    if kind in native_forms.NATIVE_FORMS:
        return visual.get("preview") or visual.get("asset"), native_forms.redraw_still(kind, spec).encode("utf-8")
    if kind == "scene3d":
        from . import scene_preview

        return visual.get("preview") or visual.get("asset"), scene_preview.render(spec)
    return None


def republish(domain: str, as_of: str, record: dict, upload: Upload) -> dict[str, Any]:
    """Re-upload the saved files of ``record``'s visuals (stills rebuilt from saved specs). ``upload`` is idempotent (hash skip), so a repeat costs nothing.
    Returns ``{"uploaded", "rebuilt", "files", "missing": [{"id","kind","theater","why"}]}``; never raises."""
    saved = load(domain, as_of)
    out: dict[str, Any] = {"uploaded": 0, "rebuilt": [], "files": 0, "missing": []}
    send: dict[str, bytes] = {}
    sections = [s for t in record.get("theaters") or [] for s in (t, *(t.get("updates") or []))]
    for sec in sections:
        for v in sec.get("visuals") or []:
            paths = _paths(v)
            try:
                rebuilt = _still(v, saved)
            except Exception as exc:  # noqa: BLE001 - one bad spec must not stop the others
                out["missing"].append({"id": v.get("id"), "kind": v.get("kind"), "theater": sec.get("theater_id"), "why": f"saved spec unreadable: {type(exc).__name__}"})
                continue
            have = {p: saved[p] for p in paths if p in saved}
            if rebuilt and rebuilt[0]:
                have[rebuilt[0]] = rebuilt[1]
                out["rebuilt"].append(v.get("id"))
            if not have:
                out["missing"].append({"id": v.get("id"), "kind": v.get("kind"), "theater": sec.get("theater_id"),
                                       "why": "no saved files (published before visuals were kept locally); needs the model calls again: intel daily --visuals-only --fresh"})
                continue
            if len(have) < len(paths):
                out["missing"].append({"id": v.get("id"), "kind": v.get("kind"), "theater": sec.get("theater_id"),
                                       "why": f"{len(paths) - len(have)} of {len(paths)} files were never saved"})
            send.update(have)
    try:
        if send:
            persist(send)                                   # rebuilt stills are kept too
            res = upload(send)
            out["uploaded"] = res.get("assets", 0)
            out["upload_note"] = res.get("note") or ("" if res.get("ok", True) else f"failed: {res.get('failed')}")
    except Exception as exc:  # noqa: BLE001
        out["upload_note"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    out["files"] = len(send)
    return out
