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

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.agent_system.agents.radar.sweep import sweep_pool
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

    st = verbs.add_parser("status", help="what is queued and when it goes")
    st.set_defaults(handler=run_status)


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

    posts = [
        q.RadarPost(key=p.source_key, text=p.text,
                    created_at=datetime.now(UTC).isoformat())
        for p in sweep.posts
    ]
    if args.dry_run:
        _print({"pool": str(path), "considered": sweep.considered, "dry_run": True,
                "would_queue": [p.text for p in posts]})
        return 0

    added, dupes = q.enqueue(posts)
    _print({
        "pool": str(path),
        "considered": sweep.considered,
        "queued": [{"id": p.id, "scheduled_for": p.scheduled_for,
                    "text": p.text} for p in added],
        "already_seen": len(dupes),
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
    _print(q.summary())
    return 0
