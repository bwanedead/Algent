"""
The briefing queue — themed menu roundups waiting to go out.

Same persistence idea as the radar queue (jsonl, spaced, survives a closed laptop)
but a different file and a different key: a briefing is identified by the portfolio
it came from plus the pillar and vector ids, not by a t0 item. Re-expressing a
Radar item is allowed; posting the same cluster twice is not.
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

from algent_backend.agent_system.agents.newsroom.flags import briefing_spacing_min

_QUEUE_ENV = "ALGENT_BRIEFING_QUEUE"
_DEFAULT_QUEUE = Path("runs_data") / "briefing_queue.jsonl"
_STATE_PATH = Path("runs_data") / "briefing_state.json"
_IMAGES = Path("runs_data") / "briefing_images"
_JITTER_MIN = 20


def queue_path() -> Path:
    return Path(os.environ.get(_QUEUE_ENV) or _DEFAULT_QUEUE)


def images_dir() -> Path:
    return _IMAGES


@dataclass
class BriefingPost:
    key: str
    pillar: str
    text: str
    t0_ref: str = ""
    vector_ids: list[str] = field(default_factory=list)
    image_path: str = ""
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


def load(path: Path | None = None) -> list[BriefingPost]:
    p = path or queue_path()
    if not p.exists():
        return []
    out: list[BriefingPost] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(BriefingPost(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def save(posts: list[BriefingPost], path: Path | None = None) -> None:
    p = path or queue_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(asdict(post), ensure_ascii=False) for post in posts) + "\n",
        encoding="utf-8",
    )


def schedule(
    new: list[BriefingPost],
    existing: list[BriefingPost],
    *,
    now: datetime | None = None,
) -> list[BriefingPost]:
    start = now or datetime.now(UTC)
    pending = [
        datetime.fromisoformat(p.scheduled_for)
        for p in existing
        if p.status == "queued" and p.scheduled_for
    ]
    cursor = max([start, *pending]) if pending else start
    gap = briefing_spacing_min()
    scheduled: list[BriefingPost] = []
    for i, post in enumerate(new):
        # First cluster of a fresh compose may go out soon; the rest keep the gap.
        wait = 2 if i == 0 and not pending else gap + random.randint(0, _JITTER_MIN)
        if i == 0 and not pending:
            cursor = start + timedelta(minutes=wait)
        else:
            cursor = cursor + timedelta(minutes=wait)
        post.scheduled_for = cursor.isoformat()
        post.created_at = post.created_at or start.isoformat()
        scheduled.append(post)
    return scheduled


def enqueue(new: list[BriefingPost], *, path: Path | None = None,
            now: datetime | None = None) -> tuple[list[BriefingPost], list[BriefingPost]]:
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


def due(path: Path | None = None, *, now: datetime | None = None) -> list[BriefingPost]:
    when = now or datetime.now(UTC)
    return [p for p in load(path) if p.due(when)]


def mark(post_id: str, *, status: str, url: str = "", note: str = "",
         image_path: str = "", path: Path | None = None) -> None:
    posts = load(path)
    for p in posts:
        if p.id == post_id:
            p.status = status  # type: ignore[assignment]
            p.post_url = url or p.post_url
            p.note = note or p.note
            p.image_path = image_path or p.image_path
            if status == "posted":
                p.posted_at = datetime.now(UTC).isoformat()
    save(posts, path)


def last_posted_at(path: Path | None = None) -> datetime | None:
    stamps = [p.posted_at for p in load(path) if p.status == "posted" and p.posted_at]
    return max(datetime.fromisoformat(s) for s in stamps) if stamps else None


def read_state() -> dict[str, Any]:
    if not _STATE_PATH.exists():
        return {}
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(state: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
