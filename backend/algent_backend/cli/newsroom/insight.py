"""
``newsroom insight`` — figure-first posts to X (chart or short GIF).

Compose never sends. Drain is the only thing that posts. The radar supervisor
calls ``daemon_tick`` so a second process is not required.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from typing import Any

from algent_backend.agent_system.agents.insight.contracts import spec_key
from algent_backend.agent_system.agents.insight.produce import already_said, produce
from algent_backend.agent_system.agents.newsroom.flags import (
    insight_compose_every_min,
    insight_enabled,
)
from algent_backend.publishing import insight_queue as q
from algent_backend.publishing import radar_queue as radar_q
from algent_backend.publishing.insight_engagement import (
    append_snapshots,
    fetch_metrics,
    tweet_id_from_url,
)
from algent_backend.publishing.x_client import XWriteError, post, upload_media, write_configured


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def add_parser(sub: Any) -> None:
    p = sub.add_parser("insight", help="figure-first chart/GIF posts to X (not Radar)")
    verbs = p.add_subparsers(dest="insight_cmd", required=True)

    c = verbs.add_parser("compose", help="commission one figure and QUEUE it")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(handler=run_compose)

    d = verbs.add_parser("drain", help="post due insight figures")
    d.add_argument("--max", type=int, default=1)
    d.add_argument("--dry-run", action="store_true")
    d.set_defaults(handler=run_drain)

    st = verbs.add_parser("status", help="what is queued, and whether the lane is on")
    st.set_defaults(handler=run_status)

    on = verbs.add_parser("start", help="turn the lane on (starts radar if it is down)")
    on.set_defaults(handler=run_start)

    off = verbs.add_parser("stop", help="pause insights; radar keeps running")
    off.set_defaults(handler=run_stop)


def lane_active() -> bool:
    return insight_enabled() and not q.paused()


def run_compose(args: Any) -> int:
    if not lane_active():
        _print({"queued": 0, "note": _off_note()})
        return 0
    added, note = compose(dry_run=args.dry_run)
    _print({
        "dry_run": bool(args.dry_run),
        "queued": [{"id": p.id, "beat": p.beat, "form": p.form, "text": p.text}
                   for p in added],
        "note": note,
    })
    return 0


def run_drain(args: Any) -> int:
    ready = sorted(q.due(), key=lambda p: p.scheduled_for or "")
    batch = ready[: max(1, args.max)]
    if args.dry_run:
        _print({"dry_run": True, "would_post": [
            {"id": p.id, "beat": p.beat, "text": p.text} for p in batch]})
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
        sent.append({"id": item.id, "url": url, "beat": item.beat})
    _print({"posted": sent, "failed": failed})
    return 0 if not failed else 1


def run_status(_args: Any) -> int:
    from algent_backend.publishing import radar_daemon as daemon

    pending = [p for p in q.load() if p.status == "queued"]
    alive, state = daemon.running()
    _print({
        "on": lane_active(),
        "paused": q.paused(),
        "standing_flag": insight_enabled(),
        "supervisor_running": alive,
        "supervisor_pid": state.pid if state and alive else None,
        "queued": len(pending),
        "due_now": len(q.due()),
        "last_posted_at": (q.last_posted_at() or datetime.min.replace(tzinfo=UTC)).isoformat()
        if q.last_posted_at() else "",
        "next": [{"id": p.id, "beat": p.beat, "scheduled_for": p.scheduled_for}
                 for p in sorted(pending, key=lambda x: x.scheduled_for or "")[:8]],
        "start_with": "python -m algent_backend.cli newsroom insight start",
        "stop_with": "python -m algent_backend.cli newsroom insight stop",
    })
    return 0


def run_start(_args: Any) -> int:
    from algent_backend.cli.newsroom import radar as radar_cli
    from algent_backend.publishing import radar_daemon as daemon

    if not insight_enabled():
        _print({"error": "insight off in flags.INSIGHT_ENABLED — that is the standing default",
                "on": False})
        return 1
    q.clear_pause()
    alive, state = daemon.running()
    started_supervisor = False
    if not alive:
        _pid, state = radar_cli.spawn_detached_loop(
            daemon.DISCOVERY_EVERY_MIN, daemon.POST_EVERY_MIN)
        started_supervisor = True
        alive, state = daemon.running()
    _print({
        "on": True,
        "paused": False,
        "supervisor_started": started_supervisor,
        "supervisor_running": alive,
        "pid": state.pid if state else None,
        "stop_with": "python -m algent_backend.cli newsroom insight stop",
        "note": "insights share radar's supervisor — no second process",
    })
    return 0 if alive else 1


def run_stop(_args: Any) -> int:
    q.request_pause()
    _print({
        "on": False,
        "paused": True,
        "note": "radar is still running; insight ticks are skipped until `insight start`",
        "start_with": "python -m algent_backend.cli newsroom insight start",
    })
    return 0


def _off_note() -> str:
    if q.paused():
        return "insight paused (`newsroom insight start` to resume)"
    return "insight off (flags.INSIGHT_ENABLED)"


def compose(*, dry_run: bool = False,
            now: datetime | None = None) -> tuple[list[q.InsightPost], str]:
    dest = q.images_dir() / datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    spec, text, media = produce(dest=dest, already=already_said(q.load()))
    state = q.read_state()
    state["composed_at"] = datetime.now(UTC).isoformat()
    if spec.beat:
        state["last_beat"] = spec.beat
    q.write_state(state)
    if not spec.warranted or not text or not media:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return [], spec.note or "not warranted"
    if dry_run:
        return [], f"would queue {spec.beat} {spec.form}: {spec.takeaway[:80]}"
    post = q.InsightPost(
        key=spec_key(spec),
        beat=spec.beat,
        form=spec.form,
        text=text,
        takeaway=spec.takeaway,
        source_url=spec.source_url,
        image_path=media,
    )
    added, dupes = q.enqueue([post], now=now)
    if dupes and not added:
        return [], "already queued or posted that takeaway"
    return added, ""


def release(item: q.InsightPost) -> str:
    media_ids: list[str] = []
    if item.image_path:
        media_ids = [upload_media(item.image_path)]
    result = post(item.text, media_ids=media_ids or None)
    q.mark(item.id, status="posted", url=result.url, image_path=item.image_path,
           tweet_id=result.id)
    return result.url


def _quiet_gap_ok(now: datetime) -> bool:
    from algent_backend.publishing import briefing_queue as briefing_q

    stamps = [q.last_posted_at(), radar_q.last_posted_at(), briefing_q.last_posted_at()]
    latest = max((s for s in stamps if s is not None), default=None)
    if latest is None:
        return True
    return now - latest >= timedelta(minutes=25)


def _should_compose(now: datetime) -> bool:
    pending = sum(1 for p in q.load() if p.status == "queued")
    if pending >= 2:
        return False
    raw = q.read_state().get("composed_at") or ""
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(raw)
    except ValueError:
        return True
    return now - last >= timedelta(minutes=insight_compose_every_min())


def _poll_engagement() -> str:
    ids = [p.tweet_id or tweet_id_from_url(p.post_url)
           for p in q.load() if p.status == "posted"]
    ids = [i for i in ids if i][-20:]
    if not ids:
        return ""
    try:
        rows = fetch_metrics(ids)
        n = append_snapshots(rows)
    except XWriteError as exc:
        return f"insight metrics skipped: {str(exc)[:120]}"
    return f"insight metrics: {n} snapshot(s)" if n else ""


def daemon_tick() -> str:
    if not lane_active():
        return ""
    now = datetime.now(UTC)
    notes = [_safe_poll()]
    notes.append(_compose_note(now))
    notes = [n for n in notes if n]
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
        notes.append(f"insight FAILED (stays queued): {str(exc)[:160]}")
        return "; ".join(notes)
    notes.append(f"insight posted ({item.beat}): {url}")
    return "; ".join(notes)


def _safe_poll() -> str:
    try:
        return _poll_engagement()
    except Exception as exc:  # noqa: BLE001
        return f"insight metrics failed: {str(exc)[:120]}"


def _compose_note(now: datetime) -> str:
    if not _should_compose(now):
        return ""
    try:
        added, note = compose(now=now)
        if added:
            return f"insight compose: {added[0].beat} queued"
        if note:
            return f"insight compose skipped: {note[:140]}"
    except Exception as exc:  # noqa: BLE001
        return f"insight compose failed: {str(exc)[:160]}"
    return ""
