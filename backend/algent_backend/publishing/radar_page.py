"""
The headline radar on the site — every synthesis menu, kept.

A built menu is already posted to X as the day's roundup; this puts the same menu on the site,
where it is readable in full, carries the outlets each lead came from, and never falls off: each
build is its own file under ``content/radar/`` and the site lists them all (operator, 09-26 —
"i dont want old menus to fall off… click through previous menus").

Same framing as the X post: these are other outlets' headlines, not verified by us. The site
states that once, at the top of every radar page.

The file is data, not markup — the site renders it — so a lead's text cannot inject anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import site_git

RADAR_SUBDIR = ("content", "radar")
_MAX_SOURCES = 3


def slug_for(built_at: str) -> str:
    """``2026-09-24T22:17:06+00:00`` → ``2026-09-24-2217`` (UTC). One file per build."""
    try:
        when = datetime.fromisoformat(built_at.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, AttributeError):
        when = datetime.now(UTC)
    return when.strftime("%Y-%m-%d-%H%M")


def menu_record(portfolio: dict[str, Any]) -> dict[str, Any]:
    """What the site shows of a menu: numbered leads, their pillars, and their sources."""
    built_at = str(portfolio.get("generated_at") or datetime.now(UTC).isoformat())
    leads = []
    for n, v in enumerate(portfolio.get("vectors") or [], 1):
        if not isinstance(v, dict) or not (v.get("title") or v.get("thesis")):
            continue
        sources = [str(u) for u in (v.get("sources") or []) if str(u).startswith("http")]
        leads.append({
            "n": n,
            "title": " ".join(str(v.get("title") or "").split()),
            "thesis": " ".join(str(v.get("thesis") or "").split()),
            "pillars": [str(p) for p in (v.get("pillars") or []) if p],
            "kind": str(v.get("vector_type") or ""),
            "sources": sources[:_MAX_SOURCES],
        })
    return {"slug": slug_for(built_at), "built_at": built_at, "leads": leads}


def write_menu(site_dir: Path, portfolio: dict[str, Any]) -> Path | None:
    """Write one menu into a site checkout. Returns the file, or None when there is nothing to show."""
    record = menu_record(portfolio)
    if not record["leads"]:
        return None
    folder = site_dir.joinpath(*RADAR_SUBDIR)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record['slug']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                    newline="\n")
    return path


def publish_menu(portfolio: dict[str, Any]) -> dict[str, Any]:
    """Put a freshly built menu live on the site. Never raises — the menu itself is already built."""
    if not site_git.publish_enabled():
        return {"published": False, "note": "site publishing disabled"}
    try:
        root = site_git.repo_root()
        worktree, note = site_git.ensure_worktree(root)
        if worktree is None:
            return {"published": False, "note": note}
        path = write_menu(site_git.live_site_dir(root), portfolio)
        if path is None:
            return {"published": False, "note": "menu had no leads"}
        ok, pushed = site_git.commit_and_push(worktree, f"radar({path.stem}): headline menu")
        return {"published": ok, "slug": path.stem, "note": pushed}
    except Exception as exc:  # noqa: BLE001
        return {"published": False, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
