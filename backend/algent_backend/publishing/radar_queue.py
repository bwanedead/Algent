"""
The radar queue — what is waiting to be posted, and when it may go.

A radar sweep produces several posts at once. Firing them together would read as a bot emptying
a buffer, so the queue spaces them.

There is no urgency tier and no fast lane. An earlier design had one, on the reasoning that a
live event is worth more early — true, but it required judging liveness from a pool line, which
the model cannot do reliably: it does not know how old the pool is, and a first sweep confidently
marked a two-day-old wildfire as live. A misclassification that GRANTS priority is worse than
having no priority, because it spends the fast lane on something stale and trains you to distrust
the flag. One cadence for everything is duller and always right.

THE UNAVOIDABLE LIMIT: this drains when something runs it, and the operator's machine is not
always on. The queue is therefore persistent and idempotent — nothing is lost while the machine
sleeps, and a drain after a long gap releases the backlog on its own spacing rather than dumping
it. Genuinely continuous posting needs an always-on host; the queue is shaped so that moving
there later changes the scheduler, not the data.
"""

from __future__ import annotations

import json
import os
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

#: Minimum gap between posts, in minutes.
_SPACING_MIN = 40
#: Jitter so a drained backlog does not go out on a metronome, which reads as automation.
_JITTER_MIN = 12

_QUEUE_ENV = "ALGENT_RADAR_QUEUE"
_DEFAULT_QUEUE = Path("runs_data") / "radar_queue.jsonl"


def queue_path() -> Path:
    return Path(os.environ.get(_QUEUE_ENV) or _DEFAULT_QUEUE)


@dataclass
class RadarPost:
    """One queued post. ``key`` is the dedup identity — the t0 item it came from."""

    key: str
    text: str
    status: Literal["queued", "posted", "failed", "skipped"] = "queued"
    scheduled_for: str = ""
    created_at: str = ""
    posted_at: str = ""
    post_url: str = ""
    note: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def due(self, now: datetime | None = None) -> bool:
        if self.status != "queued":
            return False
        if not self.scheduled_for:
            return True
        return (now or datetime.now(UTC)) >= datetime.fromisoformat(self.scheduled_for)


def load(path: Path | None = None) -> list[RadarPost]:
    p = path or queue_path()
    if not p.exists():
        return []
    out: list[RadarPost] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(RadarPost(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue  # a torn line must never take the whole queue down
    return out


def save(posts: list[RadarPost], path: Path | None = None) -> None:
    p = path or queue_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(asdict(post), ensure_ascii=False) for post in posts) + "\n",
        encoding="utf-8",
    )


def schedule(
    new: list[RadarPost],
    existing: list[RadarPost],
    *,
    now: datetime | None = None,
) -> list[RadarPost]:
    """Assign release times, evenly spaced and never behind what is already queued.

    Scheduling from the LAST pending slot rather than from now is what stops a second sweep
    from interleaving into the first one's gaps and undoing the spacing.
    """
    start = now or datetime.now(UTC)
    pending = [
        datetime.fromisoformat(p.scheduled_for)
        for p in existing
        if p.status == "queued" and p.scheduled_for
    ]
    cursor = max([start, *pending]) if pending else start

    scheduled: list[RadarPost] = []
    for post in new:
        cursor = cursor + timedelta(minutes=_SPACING_MIN + random.randint(0, _JITTER_MIN))
        post.scheduled_for = cursor.isoformat()
        post.created_at = post.created_at or start.isoformat()
        scheduled.append(post)
    return scheduled


def enqueue(new: list[RadarPost], *, path: Path | None = None,
            now: datetime | None = None) -> tuple[list[RadarPost], list[RadarPost]]:
    """Add posts, dropping any whose ``key`` we have already queued. Returns (added, duplicates).

    Dedup is by source key rather than text: the same t0 item can be phrased two ways across
    sweeps, and posting it twice is the failure, not the wording.
    """
    existing = load(path)
    seen = {p.key for p in existing if p.key}
    added, dupes = [], []
    for post in new:
        (dupes if post.key in seen else added).append(post)
        seen.add(post.key)
    if added:
        schedule(added, existing, now=now)
        save(existing + added, path)
    return added, dupes


def due(path: Path | None = None, *, now: datetime | None = None) -> list[RadarPost]:
    when = now or datetime.now(UTC)
    return [p for p in load(path) if p.due(when)]


def mark(post_id: str, *, status: str, url: str = "", note: str = "",
         path: Path | None = None) -> None:
    posts = load(path)
    for p in posts:
        if p.id == post_id:
            p.status = status  # type: ignore[assignment]
            p.post_url = url or p.post_url
            p.note = note or p.note
            if status == "posted":
                p.posted_at = datetime.now(UTC).isoformat()
    save(posts, path)


def summary(path: Path | None = None) -> dict[str, Any]:
    posts = load(path)
    counts: dict[str, int] = {}
    for p in posts:
        counts[p.status] = counts.get(p.status, 0) + 1
    nxt = sorted(
        (p for p in posts if p.status == "queued" and p.scheduled_for),
        key=lambda p: p.scheduled_for,
    )
    return {
        "total": len(posts),
        "by_status": counts,
        "next_due": nxt[0].scheduled_for if nxt else "",
        "queued": [
            {"id": p.id, "scheduled_for": p.scheduled_for, "text": p.text[:80]}
            for p in nxt[:10]
        ],
    }
