"""The insight queue — figure-first posts waiting to go out.

Same persistence idea as briefing (jsonl, spaced, survives a closed laptop) with a
different key: beat + as-of + takeaway, not a t0 item.
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

from algent_backend.agent_system.runs.control_plane.fsio import atomic_write_text

_QUEUE_ENV = "ALGENT_INSIGHT_QUEUE"
_DEFAULT_QUEUE = Path("runs_data") / "insight_queue.jsonl"
_STATE_PATH = Path("runs_data") / "insight_state.json"
_IMAGES = Path("runs_data") / "insight_images"
PAUSE_FILE = Path("runs_data") / "insight.pause"
_JITTER_MIN = 25


def queue_path() -> Path:
    return Path(os.environ.get(_QUEUE_ENV) or _DEFAULT_QUEUE)


def images_dir() -> Path:
    return _IMAGES


@dataclass
class InsightPost:
    key: str
    beat: str
    form: str
    text: str
    takeaway: str = ""
    source_url: str = ""
    image_path: str = ""
    status: Literal["queued", "posted", "failed", "skipped"] = "queued"
    scheduled_for: str = ""
    created_at: str = ""
    posted_at: str = ""
    post_url: str = ""
    tweet_id: str = ""
    note: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def due(self, now: datetime | None = None) -> bool:
        if self.status != "queued":
            return False
        if not self.scheduled_for:
            return True
        return (now or datetime.now(UTC)) >= datetime.fromisoformat(self.scheduled_for)


def load(path: Path | None = None) -> list[InsightPost]:
    p = path or queue_path()
    if not p.exists():
        return []
    out: list[InsightPost] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(InsightPost(**json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


def save(posts: list[InsightPost], path: Path | None = None) -> None:
    p = path or queue_path()
    body = "\n".join(json.dumps(asdict(post), ensure_ascii=False) for post in posts) + "\n"
    atomic_write_text(p, body)


def spacing_min() -> int:
    from algent_backend.agent_system.agents.newsroom.flags import insight_spacing_min
    return insight_spacing_min()


def schedule(
    new: list[InsightPost],
    existing: list[InsightPost],
    *,
    now: datetime | None = None,
) -> list[InsightPost]:
    start = now or datetime.now(UTC)
    pending = [
        datetime.fromisoformat(p.scheduled_for)
        for p in existing
        if p.status == "queued" and p.scheduled_for
    ]
    cursor = max([start, *pending]) if pending else start
    gap = spacing_min()
    scheduled: list[InsightPost] = []
    for i, post in enumerate(new):
        wait = 8 if i == 0 and not pending else gap + random.randint(0, _JITTER_MIN)
        if i == 0 and not pending:
            cursor = start + timedelta(minutes=wait)
        else:
            cursor = cursor + timedelta(minutes=wait)
        post.scheduled_for = cursor.isoformat()
        post.created_at = post.created_at or start.isoformat()
        scheduled.append(post)
    return scheduled


def enqueue(new: list[InsightPost], *, path: Path | None = None,
            now: datetime | None = None) -> tuple[list[InsightPost], list[InsightPost]]:
    existing = load(path)
    seen = {p.key for p in existing if p.key}
    added, dupes = [], []
    for post in new:
        if post.key in seen:
            dupes.append(post)
            continue
        added.append(post)
        seen.add(post.key)
    if added:
        schedule(added, existing, now=now)
        save(existing + added, path)
    return added, dupes


def due(path: Path | None = None, *, now: datetime | None = None) -> list[InsightPost]:
    when = now or datetime.now(UTC)
    return [p for p in load(path) if p.due(when)]


def mark(post_id: str, *, status: str, url: str = "", note: str = "",
         image_path: str = "", tweet_id: str = "", path: Path | None = None) -> None:
    posts = load(path)
    for p in posts:
        if p.id == post_id:
            p.status = status  # type: ignore[assignment]
            p.post_url = url or p.post_url
            p.note = note or p.note
            p.image_path = image_path or p.image_path
            p.tweet_id = tweet_id or p.tweet_id
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
    atomic_write_text(_STATE_PATH, json.dumps(state, indent=2))


def paused() -> bool:
    return PAUSE_FILE.exists()


def request_pause() -> None:
    PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")


def clear_pause() -> None:
    PAUSE_FILE.unlink(missing_ok=True)
