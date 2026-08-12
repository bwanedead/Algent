"""
``newsroom briefing`` — themed menu roundups to X, with a collage image.

Compose never sends. Drain is the only thing that posts. The radar supervisor
calls ``daemon_tick`` so a second process is not required.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from algent_backend.agent_system.agents.briefing.compose import (
    collage_setting,
    collage_subject,
    cluster_portfolio,
    format_briefing,
)
from algent_backend.agent_system.agents.editorial.hero_image import check_subject
from algent_backend.agent_system.agents.newsroom.flags import briefing_enabled
from algent_backend.publishing import briefing_queue as q
from algent_backend.publishing import radar_queue as radar_q
from algent_backend.publishing.x_client import XWriteError, post, upload_media, write_configured


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def add_parser(sub: Any) -> None:
    p = sub.add_parser("briefing", help="themed t1-menu roundups to X (not Radar)")
    verbs = p.add_subparsers(dest="briefing_cmd", required=True)

    c = verbs.add_parser("compose", help="cluster the latest (or pinned) menu and QUEUE posts")
    c.add_argument("--menu", help="portfolio JSON or discovery_synthesis run dir")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(handler=run_compose)

    d = verbs.add_parser("drain", help="post due briefings (one image + one post each)")
    d.add_argument("--max", type=int, default=1)
    d.add_argument("--dry-run", action="store_true")
    d.set_defaults(handler=run_drain)

    st = verbs.add_parser("status", help="what is queued")
    st.set_defaults(handler=run_status)


def run_compose(args: Any) -> int:
    if not briefing_enabled():
        _print({"queued": 0, "note": "briefing off (flags.BRIEFING_ENABLED)"})
        return 0
    try:
        added, dupes, t0_ref = compose(menu=args.menu, dry_run=args.dry_run)
    except (FileNotFoundError, ValueError) as exc:
        _print({"error": str(exc)})
        return 1
    _print({
        "t0_ref": t0_ref,
        "dry_run": bool(args.dry_run),
        "queued": [{"id": p.id, "pillar": p.pillar, "scheduled_for": p.scheduled_for,
                    "text": p.text} for p in added],
        "already_seen": len(dupes),
    })
    return 0


def run_drain(args: Any) -> int:
    ready = sorted(q.due(), key=lambda p: p.scheduled_for or "")
    batch = ready[: max(1, args.max)]
    if args.dry_run:
        _print({"dry_run": True, "would_post": [
            {"id": p.id, "pillar": p.pillar, "text": p.text} for p in batch]})
        return 0
    if not batch:
        _print({"posted": [], "note": "nothing due"})
        return 0
    if not write_configured():
        _print({"error": "X write credentials are not configured"})
        return 1
    sent, failed = [], []
    for item in batch:
        try:
            url = release(item)
        except XWriteError as exc:
            q.mark(item.id, status="queued", note=str(exc)[:200])
            failed.append({"id": item.id, "error": str(exc)[:200]})
            break
        sent.append({"id": item.id, "url": url, "pillar": item.pillar})
    _print({"posted": sent, "failed": failed})
    return 0 if not failed else 1


def run_status(_args: Any) -> int:
    pending = [p for p in q.load() if p.status == "queued"]
    _print({
        "enabled": briefing_enabled(),
        "queued": len(pending),
        "due_now": len(q.due()),
        "last_posted_at": (q.last_posted_at() or datetime.min.replace(tzinfo=UTC)).isoformat()
        if q.last_posted_at() else "",
        "next": [{"id": p.id, "pillar": p.pillar, "scheduled_for": p.scheduled_for}
                 for p in sorted(pending, key=lambda x: x.scheduled_for or "")[:8]],
        "last_composed_t0": q.read_state().get("t0_ref", ""),
    })
    return 0


def compose(*, menu: str | None = None, dry_run: bool = False,
            now: datetime | None = None) -> tuple[list[q.BriefingPost], list[q.BriefingPost], str]:
    from algent_backend.cli.newsroom.pipeline import load_portfolio

    portfolio, _path = load_portfolio(menu)
    t0_ref = str(portfolio.get("t0_ref") or portfolio.get("generated_at") or "")
    posts = [
        q.BriefingPost(
            key=cluster.key(t0_ref),
            pillar=cluster.pillar,
            text=format_briefing(cluster.pillar, cluster.vectors),
            t0_ref=t0_ref,
            vector_ids=list(cluster.vector_ids),
        )
        for cluster in cluster_portfolio(portfolio)
    ]
    if dry_run:
        return posts, [], t0_ref
    added, dupes = q.enqueue(posts, now=now)
    state = q.read_state()
    state["t0_ref"] = t0_ref
    state["composed_at"] = datetime.now(UTC).isoformat()
    q.write_state(state)
    return added, dupes, t0_ref


def release(item: q.BriefingPost) -> str:
    """Generate the collage if needed, then post. Text still ships if the image fails."""
    media_ids: list[str] = []
    image_path = item.image_path
    if not image_path:
        image_path = _render_collage(item) or ""
    if image_path:
        try:
            media_ids = [upload_media(image_path)]
        except XWriteError:
            media_ids = []
    result = post(item.text, media_ids=media_ids or None)
    q.mark(item.id, status="posted", url=result.url, image_path=image_path)
    return result.url


def _render_collage(item: q.BriefingPost) -> str | None:
    """One hero-image call. Subject is a pillar scene, never the menu copy."""
    from algent_backend.agent_system.agents.editorial.image_gen import (
        ImageGenerationError,
        generate_hero_image,
    )

    subject = collage_subject(item.pillar)
    if check_subject(subject):
        return None
    try:
        image = generate_hero_image(subject, setting=collage_setting())
    except (ImageGenerationError, Exception):  # noqa: BLE001 — a missing picture must not kill the post
        return None
    folder = q.images_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{item.id}{image.suffix()}"
    path.write_bytes(image.data)
    return str(path)


def _quiet_gap_ok(now: datetime) -> bool:
    """Do not fire a briefing in the same breath as a Radar post."""
    stamps = [q.last_posted_at(), radar_q.last_posted_at()]
    latest = max((s for s in stamps if s is not None), default=None)
    if latest is None:
        return True
    return now - latest >= timedelta(minutes=20)


def daemon_tick() -> str:
    """Supervisor hook: compose if the menu is new, release at most one due briefing."""
    if not briefing_enabled():
        return ""
    now = datetime.now(UTC)
    notes: list[str] = []
    try:
        from algent_backend.cli.newsroom.pipeline import load_portfolio
        portfolio, _ = load_portfolio()
        t0_ref = str(portfolio.get("t0_ref") or "")
        if t0_ref and t0_ref != q.read_state().get("t0_ref"):
            added, _, ref = compose()
            if added:
                notes.append(f"briefing compose: {len(added)} roundup(s) queued from {ref}")
    except (FileNotFoundError, ValueError):
        pass
    except Exception as exc:  # noqa: BLE001
        return f"briefing compose failed (continuing): {str(exc)[:160]}"

    if not _quiet_gap_ok(now):
        return "; ".join(notes)
    ready = sorted(q.due(now=now), key=lambda p: p.scheduled_for or "")
    if not ready or not write_configured():
        return "; ".join(notes)
    item = ready[0]
    try:
        url = release(item)
    except XWriteError as exc:
        q.mark(item.id, status="queued", note=str(exc)[:200])
        notes.append(f"briefing FAILED (stays queued): {str(exc)[:160]}")
        return "; ".join(notes)
    notes.append(f"briefing posted ({item.pillar}): {url}")
    return "; ".join(notes)
