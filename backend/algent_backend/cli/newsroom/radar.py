"""
``newsroom radar`` — the light lane: t0 pool -> short posts -> X, no article.

Two verbs, deliberately separate:

- ``sweep`` judges a pool and QUEUES posts. It never sends, so a sweep can run right after t0
  without deciding what the timeline looks like for the next two hours.
- ``drain`` sends whatever is due. It is the only thing that posts, it is idempotent, and it is
  safe to run on a timer or by hand.

Splitting them is what makes the schedule survive an operator whose machine is not always on:
the sweep's judgement is captured when the pool is fresh, and release is a separate concern that
catches up gracefully after a gap.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.agent_system.agents.radar.sweep import sweep_pool
from algent_backend.agent_system.agents.radar.verify import apply_checks, check_posts
from algent_backend.agent_system.runs.control_plane.process_tree import terminate_tree
from algent_backend.publishing import radar_daemon as daemon
from algent_backend.publishing import radar_queue as q
from algent_backend.publishing.x_client import XWriteError, post, write_configured


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def add_parser(sub: Any) -> None:
    p = sub.add_parser("radar", help="light lane: t0 pool -> short X posts (no article)")
    verbs = p.add_subparsers(dest="radar_cmd", required=True)

    s = verbs.add_parser("sweep", help="judge the latest t0 pool and QUEUE posts (never sends)")
    s.add_argument("--pool", help="pool JSON (default: the newest in ingestion_data/pool)")
    s.add_argument("--dry-run", action="store_true", help="show what would be queued")
    s.set_defaults(handler=run_sweep)

    d = verbs.add_parser("drain", help="post everything currently due")
    d.add_argument("--max", type=int, default=3,
                   help="most posts to send in one drain (default 3)")
    d.add_argument("--dry-run", action="store_true", help="show what would be sent")
    d.set_defaults(handler=run_drain)

    st = verbs.add_parser("status", help="what is queued, and whether radar is running")
    st.set_defaults(handler=run_status)

    on = verbs.add_parser("start", help="run continuously in the background until stopped")
    on.add_argument("--discovery-every", type=int, default=daemon.DISCOVERY_EVERY_MIN,
                    help="minutes between discovery refreshes")
    on.add_argument("--post-every", type=int, default=daemon.POST_EVERY_MIN,
                    help="average minutes between posts (jittered)")
    on.add_argument("--foreground", action="store_true",
                    help="run in this terminal instead of detaching (Ctrl-C to stop)")
    on.set_defaults(handler=run_start)

    off = verbs.add_parser("stop", help="stop the background radar and verify it is gone")
    off.set_defaults(handler=run_stop)

    lp = verbs.add_parser("loop", help=argparse.SUPPRESS)
    lp.add_argument("--discovery-every", type=int, default=daemon.DISCOVERY_EVERY_MIN)
    lp.add_argument("--post-every", type=int, default=daemon.POST_EVERY_MIN)
    lp.set_defaults(handler=run_loop)


def _checked(pool: dict, sweep: Any) -> tuple[list[Any], list[dict[str, str]]]:
    """Sweep output -> queue-ready posts, with every one measured against its source line.

    Radar has no research pass, so this is the only thing standing between a wire line and a
    published sentence. It runs on BOTH paths (manual sweep and the daemon) rather than at the
    call sites, because a check that can be bypassed by using the other verb is not a check.
    """
    labels = {i.get("id"): str(i.get("label") or "")
              for i in (pool.get("items") or []) if isinstance(i, dict)}
    # Dedup by source id cannot see that two wire lines are the same story, so the check is
    # shown what recently went out and judges by the event instead.
    recent = [p.text for p in q.load() if p.status in ("posted", "queued")]
    checks = check_posts(
        [(p.source_key, p.text, labels.get(p.source_key, "")) for p in sweep.posts],
        recent=recent,
    )
    return apply_checks(list(sweep.posts), checks)


def _latest_pool() -> Path | None:
    pools = sorted(Path("ingestion_data/pool").glob("pool_*.json"))
    return pools[-1] if pools else None


def run_sweep(args: Any) -> int:
    path = Path(args.pool) if args.pool else _latest_pool()
    if path is None or not path.exists():
        _print({"error": "no t0 pool found — run `newsroom run --from t0 --to menu` first"})
        return 1

    pool = json.loads(path.read_text(encoding="utf-8"))
    # Sweeps see what has already been queued, so re-sweeping the same pool is a no-op rather
    # than a duplicate — pools are deliberately reused across runs.
    seen = {p.key for p in q.load()}
    sweep = sweep_pool(pool, already_posted=seen)
    survived, rejected = _checked(pool, sweep)

    posts = [
        q.RadarPost(key=p.source_key, text=p.text,
                    created_at=datetime.now(UTC).isoformat())
        for p in survived
    ]
    if args.dry_run:
        _print({"pool": str(path), "considered": sweep.considered, "dry_run": True,
                "would_queue": [p.text for p in posts], "rejected": rejected})
        return 0

    added, dupes = q.enqueue(posts)
    _print({
        "pool": str(path),
        "considered": sweep.considered,
        "queued": [{"id": p.id, "scheduled_for": p.scheduled_for,
                    "text": p.text} for p in added],
        "already_seen": len(dupes),
        "rejected": rejected,
        "note": sweep.note,
    })
    return 0


def run_drain(args: Any) -> int:
    ready = q.due()
    if not ready:
        _print({"posted": [], "note": "nothing due", **q.summary()})
        return 0
    # Oldest scheduled first, so a backlog drains in the order it was judged.
    ready.sort(key=lambda p: p.scheduled_for or "")
    batch = ready[: max(1, args.max)]

    if args.dry_run:
        _print({"dry_run": True,
                "would_post": [{"id": p.id, "text": p.text} for p in batch]})
        return 0
    if not write_configured():
        _print({"error": "X write credentials are not configured (X_API_KEY, X_API_KEY_SECRET, "
                         "X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)"})
        return 1

    sent, failed = [], []
    for item in batch:
        try:
            result = post(item.text)
        except XWriteError as exc:
            # Leave it QUEUED: a transient refusal should be retried on the next drain, not
            # silently dropped. Only a hard rejection of the text itself is worth burning.
            q.mark(item.id, status="queued", note=str(exc)[:200])
            failed.append({"id": item.id, "error": str(exc)[:200]})
            break  # one failure usually means all of them will fail; stop spending
        q.mark(item.id, status="posted", url=result.url)
        sent.append({"id": item.id, "url": result.url, "text": item.text})

    _print({"posted": sent, "failed": failed, **q.summary()})
    return 0 if not failed else 1


def run_status(_args: Any) -> int:
    alive, state = daemon.running()
    pending = [p for p in q.load() if p.status == "queued"]
    ready = q.due()
    out: dict[str, Any] = {
        "radar_running": alive,
        "overdue_now": len(ready),
        # Visible so a growing backlog is noticed before it becomes a timeline full of
        # yesterday's news. No pruning yet - the shape of the problem decides the rule.
        "oldest_queued_hours": round(
            max(((datetime.now(UTC) - datetime.fromisoformat(p.created_at)).total_seconds()
                 for p in pending if p.created_at), default=0.0) / 3600.0, 1),
        "queue": q.summary(),
    }
    if state is not None:
        out["daemon"] = {
            "pid": state.pid,
            "started_at": state.started_at,
            "last_discovery_at": state.last_discovery_at,
            "last_post_at": state.last_post_at,
            "next_post_at": state.next_post_at,
            "posts_sent": state.posts_sent,
            "sweeps_run": state.sweeps_run,
            "stopped_at": state.stopped_at,
            "recent_errors": state.errors[-3:],
        }
        if not alive and not state.stopped_at:
            out["note"] = ("radar is NOT running - the process is gone but never recorded a "
                           "stop, so it was killed or the machine slept. Nothing was lost; the "
                           "queue is on disk and `radar start` resumes.")
    out["log"] = str(daemon.LOG_FILE)
    _print(out)
    return 0


def run_start(args: Any) -> int:
    alive, state = daemon.running()
    if alive and state is not None:
        _print({"error": f"radar is already running (pid {state.pid}) - `radar stop` first",
                "started_at": state.started_at})
        return 1

    daemon.clear_stop()
    if args.foreground:
        return run_loop(args)

    # Detached, so closing this terminal does not take radar with it. Its output goes to the
    # log, which is the operator's only window once this command returns.
    argv = [sys.executable, "-m", "algent_backend.cli", "newsroom", "radar", "loop",
            "--discovery-every", str(args.discovery_every),
            "--post-every", str(args.post_every)]
    kwargs: dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                              "stdin": subprocess.DEVNULL, "cwd": os.getcwd()}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0))
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(argv, **kwargs)

    for _ in range(20):          # let the child record its own pid so we report a real one
        time.sleep(0.25)
        alive, state = daemon.running()
        if alive and state is not None:
            break
    _print({
        "started": True,
        "pid": state.pid if state else proc.pid,
        "discovery_every_min": args.discovery_every,
        "post_every_min": f"~{args.post_every} (jittered +/-{daemon.POST_JITTER_MIN})",
        "log": str(daemon.LOG_FILE),
        "stop_with": "python -m algent_backend.cli newsroom radar stop",
        "note": "closing the laptop just ends it - nothing is lost, the queue stays on disk",
    })
    return 0


def run_stop(_args: Any) -> int:
    report = daemon.stop()
    alive, _ = daemon.running()
    report["verified_not_running"] = not alive
    report["queue"] = q.summary()
    _print(report)
    return 0 if report.get("stopped") else 1


def run_loop(args: Any) -> int:
    """The supervisor: discovery on one clock, posting on another."""
    state = daemon.DaemonState(
        pid=os.getpid(),
        started_at=datetime.now(UTC).isoformat(),
        discovery_every_min=args.discovery_every,
        post_every_min=args.post_every,
    )
    daemon.write_state(state)
    daemon.log(f"radar started (pid {state.pid}) - discovery every {args.discovery_every}m, "
               f"posting about every {args.post_every}m")

    # RESUME, do not restart. The queue outlived the last process — a closed laptop, a kill, a
    # crash — and its schedule is still on disk, so anything whose slot has passed is due NOW.
    # Waiting a fresh interval before looking would strand a backlog for another cycle.
    #
    # It cannot burst: a release tick sends exactly ONE post, so ten overdue items go out one
    # per tempo interval rather than all at once. That is the whole reason the release is capped
    # at one rather than "everything due".
    # The tempo has to survive a restart, and the daemon's own state does not: a fresh process
    # starts with last_post_at empty, so "release one if overdue" fired the moment radar came
    # back regardless of having posted minutes earlier. Three restarts in an hour produced posts
    # 22 and then 6 minutes apart.
    #
    # So the clock is read from the QUEUE, which is the durable record of what actually went
    # out. That also survives losing the pid file entirely.
    now = datetime.now(UTC)
    gap = timedelta(minutes=args.post_every)
    earliest = (_last_sent_at() + gap) if _last_sent_at() else now
    overdue = q.due()
    if overdue and earliest <= now:
        next_post = now
        daemon.log(f"resuming with {len(overdue)} post(s) overdue - releasing one now, "
                   f"then back to the normal tempo")
    elif overdue:
        next_post = earliest
        daemon.log(f"resuming with {len(overdue)} post(s) overdue - last post was recent, "
                   f"so the next goes out at {earliest.strftime('%H:%M')}Z")
    else:
        next_post = now + timedelta(minutes=_jitter(args.post_every))
    state.next_post_at = next_post.isoformat()
    daemon.write_state(state)

    try:
        while not daemon.stop_requested():
            now = datetime.now(UTC)

            if _stale(state.last_discovery_at, args.discovery_every, now):
                deferred = False
                try:
                    queued = _refresh(state)
                    deferred = queued < 0
                    if not deferred:
                        daemon.log(f"discovery + sweep: {queued} new post(s) queued")
                except Exception as exc:  # noqa: BLE001 - a bad cycle must not end the daemon
                    state.errors.append(f"{now.isoformat()} discovery: {str(exc)[:160]}")
                    daemon.log(f"discovery FAILED (continuing): {str(exc)[:160]}")
                # A deferral is not a completed cycle: leave the clock alone so the next tick
                # tries again, instead of waiting another full interval.
                if not deferred:
                    state.last_discovery_at = now.isoformat()
                daemon.write_state(state)

            if datetime.now(UTC) >= next_post and not daemon.stop_requested():
                sent = _release_one(state)
                if sent:
                    daemon.log(f"posted: {sent}")
                next_post = datetime.now(UTC) + timedelta(minutes=_jitter(args.post_every))
                state.next_post_at = next_post.isoformat()
                daemon.write_state(state)

            time.sleep(daemon.HEARTBEAT_S)
    except KeyboardInterrupt:
        daemon.log("radar interrupted from the terminal")

    state.stopped_at = datetime.now(UTC).isoformat()
    daemon.write_state(state)
    daemon.clear_stop()
    daemon.log(f"radar stopped cleanly - {state.posts_sent} post(s) sent this session")
    return 0


def _last_sent_at() -> datetime | None:
    """When a post last actually went out, from the queue rather than daemon memory."""
    stamps = [p.posted_at for p in q.load() if p.status == "posted" and p.posted_at]
    return max(datetime.fromisoformat(s) for s in stamps) if stamps else None


def _jitter(minutes: int) -> float:
    """A window around the target, so the timeline never shows a post on the hour every hour."""
    return max(1.0, minutes + random.uniform(-daemon.POST_JITTER_MIN, daemon.POST_JITTER_MIN))


def _stale(stamp: str, every_min: int, now: datetime) -> bool:
    if not stamp:
        return True
    return now - datetime.fromisoformat(stamp) >= timedelta(minutes=every_min)


def _rail_busy() -> bool:
    """Is a newsroom run already holding the single-flight lock?"""
    from algent_backend.agent_system.runs.control_plane.liveness import process_alive

    try:
        pid = int(json.loads(
            Path("runs_data/newsroom_run.lock").read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(pid) and process_alive(pid)


def _refresh(state: daemon.DaemonState) -> int:
    """Build a fresh t0 pool, then sweep it into the queue. Returns how many were queued.

    Returns -1 when it DEFERRED: radar is the background job, so it yields to an article run
    rather than racing it for the lock. Otherwise the operator would have to remember to stop
    radar before doing any foreground work, which is exactly the kind of thing nobody remembers.
    Posting is unaffected either way — only discovery touches the rail.
    """
    if _rail_busy():
        # Log the deferral ONCE per stretch. Not advancing the discovery clock is deliberate —
        # losing a race should cost seconds, not another full interval — but it means this is
        # re-attempted every heartbeat, and saying so every five seconds buries the log the
        # operator relies on when no agent is available.
        if not _refresh.deferred:  # type: ignore[attr-defined]
            daemon.log("discovery deferred - a newsroom run holds the lock; retrying quietly")
            _refresh.deferred = True  # type: ignore[attr-defined]
        return -1
    if _refresh.deferred:  # type: ignore[attr-defined]
        daemon.log("rail free again - resuming discovery")
        _refresh.deferred = False  # type: ignore[attr-defined]
    # Popen + poll rather than subprocess.run, so a stop request is honoured DURING discovery.
    # A blocking call here meant the loop could not see the stop file for the several minutes a
    # t0 sweep takes, which made every stop in that window a force-kill — including the one
    # right after `start`, since discovery always runs first.
    child = subprocess.Popen(
        [sys.executable, "-m", "algent_backend.cli", "newsroom", "run",
         "--from", "t0", "--to", "menu", "--pool-menu", "--fresh"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 45 * 60
    while child.poll() is None:
        if daemon.stop_requested() or time.monotonic() > deadline:
            terminate_tree(child.pid)
            child.wait(timeout=10)
            # A tree-killed t0 cannot release its own single-flight lock. The next run's
            # stale-pid recovery would reclaim it anyway, but an operator checking by hand
            # should not find a lock file implying a run that is not happening.
            _clear_dead_run_lock()
            daemon.log("discovery cancelled" if daemon.stop_requested() else "discovery timed out")
            return 0
        time.sleep(2)
    path = _latest_pool()
    if path is None:
        return 0
    pool = json.loads(path.read_text(encoding="utf-8"))
    sweep = sweep_pool(pool, already_posted={p.key for p in q.load()})
    survived, rejected = _checked(pool, sweep)
    for item in rejected:
        daemon.log(f"post rejected ({item['verdict']}): {item['reason'][:120]}")
    added, _ = q.enqueue([
        q.RadarPost(key=p.source_key, text=p.text, created_at=datetime.now(UTC).isoformat())
        for p in survived
    ])
    state.sweeps_run += 1
    return len(added)


def _release_one(state: daemon.DaemonState) -> str:
    """Send at most one due post. One at a time is what keeps the cadence honest."""
    ready = sorted(q.due(), key=lambda p: p.scheduled_for or "")
    if not ready or not write_configured():
        return ""
    item = ready[0]
    try:
        result = post(item.text)
    except XWriteError as exc:
        q.mark(item.id, status="queued", note=str(exc)[:200])
        state.errors.append(f"{datetime.now(UTC).isoformat()} post: {str(exc)[:160]}")
        daemon.log(f"post FAILED (stays queued, will retry): {str(exc)[:160]}")
        return ""
    q.mark(item.id, status="posted", url=result.url)
    state.posts_sent += 1
    state.last_post_at = datetime.now(UTC).isoformat()
    return result.url


_refresh.deferred = False  # type: ignore[attr-defined]


def _clear_dead_run_lock() -> None:
    """Remove the newsroom run lock if the process it names is gone."""
    from algent_backend.agent_system.runs.control_plane.liveness import process_alive

    lock = Path("runs_data/newsroom_run.lock")
    try:
        pid = int(json.loads(lock.read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return
    if pid and not process_alive(pid):
        lock.unlink(missing_ok=True)
