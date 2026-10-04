"""
Each article figure as its own X post.

The hero card remains the article announcement. Charts get a second beat: the figure is
the post, and the article URL is a reply so the chart can be looked at on its own.

X cannot take SVG. The analytics worker copies a PNG raster when the drawer wrote one;
without that file the figure is skipped rather than uploaded as a broken attachment.

Never fatal. Same rule as the article announce: a distribution miss must not
retroactively fail a piece the newsroom already published.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .x_article import article_url

LEDGER = Path("runs_data") / "x_figures.jsonl"
_RASTER = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_IMAGE_KINDS = {"chart", "image"}


@dataclass(frozen=True)
class Figure:
    request_id: str
    title: str
    media_path: Path


def figures_from_run(run_dir: Path | str) -> list[Figure]:
    """Produced chart/image artifacts that have a raster X can upload."""
    root = Path(run_dir)
    path = root / "artifacts" / "analytics_artifacts.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    if not isinstance(rows, list):
        return []
    out: list[Figure] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "produced" or row.get("kind") not in _IMAGE_KINDS:
            continue
        media = _raster_path(root, row)
        if media is None:
            continue
        title = str(row.get("title") or "").strip()
        rid = str(row.get("request_id") or media.stem)
        if not title:
            continue
        out.append(Figure(request_id=rid, title=title, media_path=media))
    return out


def _raster_path(run_dir: Path, row: dict[str, Any]) -> Path | None:
    """``raster_name`` is canonical. Sibling walk is a one-release backfill for older runs."""
    arts = run_dir / "artifacts"
    named = str(row.get("raster_name") or "").strip()
    if named:
        cand = arts / named
        if cand.is_file() and cand.suffix.lower() in _RASTER:
            return cand
        return None
    artifact = str(row.get("artifact_name") or "").strip()
    if artifact:
        cand = arts / artifact
        if cand.is_file() and cand.suffix.lower() in _RASTER:
            return cand
        sibling = cand.with_suffix(".png")
        if sibling.is_file():
            return sibling
    return None


def already_posted(slug: str, request_id: str) -> bool:
    if not slug or not request_id or not LEDGER.exists():
        return False
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("slug") == slug and row.get("request_id") == request_id:
            return True
    return False


def _record(slug: str, request_id: str, post_url: str, reply_url: str) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "slug": slug,
            "request_id": request_id,
            "post_url": post_url,
            "reply_url": reply_url,
            "posted_at": datetime.now(UTC).isoformat(),
        }, ensure_ascii=False) + "\n")


def announce_figures(slug: str, run_dir: Path | str) -> dict[str, Any]:
    """Post each figure, then reply with the article URL. Never raises."""
    from .x_client import XWriteError, post, upload_media, write_configured

    if not slug:
        return {"posted": 0, "reason": "no slug"}
    if not write_configured():
        return {"posted": 0, "reason": "X write credentials not configured"}

    figures = figures_from_run(run_dir)
    if not figures:
        return {"posted": 0, "reason": "no raster figures"}

    posted: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for fig in figures:
        if already_posted(slug, fig.request_id):
            skipped.append({"request_id": fig.request_id, "reason": "already posted"})
            continue
        try:
            media_id = upload_media(fig.media_path)
            result = post(fig.title, media_ids=[media_id])
        except XWriteError as exc:
            skipped.append({"request_id": fig.request_id, "reason": str(exc)[:200]})
            continue
        # Record the figure even if the reply fails — resume must not post the chart again.
        reply_url = ""
        try:
            reply = post(article_url(slug), reply_to=result.id, verify_identity=False)
            reply_url = reply.url
        except XWriteError as exc:
            skipped.append({
                "request_id": fig.request_id,
                "reason": f"reply failed: {str(exc)[:180]}",
            })
        _record(slug, fig.request_id, result.url, reply_url)
        posted.append({
            "request_id": fig.request_id,
            "post_url": result.url,
            "reply_url": reply_url,
        })
    return {"posted": len(posted), "figures": posted, "skipped": skipped}
