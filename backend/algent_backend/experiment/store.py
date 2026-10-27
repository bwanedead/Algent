"""
The experiment store: write-once and append-only files, so a result cannot be quietly improved after the fact and an audit never re-derives anything.

    questions/<id>.json   snapshots/<digest>.json   policies/<digest>.json   protocols/<id>.json   resolutions/<qid>.json
    branches/<id>/branch.json + memory.jsonl (private to that branch)         observations/<id>.json (shared L2)
    runs/<run id>/{run,manifest,output}.json + prompt.txt
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ENV = "ALGENT_EXPERIMENT_STORE"


class Immutable(Exception):
    """A write-once file already exists with different content."""


def root() -> Path:
    return Path(os.environ.get(ENV) or "experiment_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_time(text: str) -> datetime | None:
    """An ISO instant. A bare date means the END of that day: a document dated the cutoff day may have appeared after the cutoff instant."""
    t = (text or "").strip()
    if not t:
        return None
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    if len(t) == 10:
        d = d.replace(hour=23, minute=59, second=59)
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def canonical(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj: Any) -> str:
    return hashlib.sha256((obj if isinstance(obj, str) else canonical(obj)).encode("utf-8")).hexdigest()[:16]


def path(rel: str) -> Path:
    return root() / rel


def write_once(rel: str, obj: Any) -> Path:
    """Write ``obj`` (a model, dict or text) at ``rel``. The same content again is a no-op; different content raises ``Immutable``."""
    text = obj if isinstance(obj, str) else json.dumps(json.loads(canonical(obj)), sort_keys=True, indent=1, ensure_ascii=False)
    p = path(rel)
    if p.exists():
        if p.read_text(encoding="utf-8") != text:
            raise Immutable(f"{rel} already exists with different content")
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))           # bytes, so the file (and its digest) is the same on every OS
    return p


def read_json(rel: str) -> Any | None:
    try:
        return json.loads(path(rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def exists(rel: str) -> bool:
    return path(rel).exists()


def append(rel: str, obj: Any) -> None:
    p = path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical(obj) + "\n")


def read_lines(rel: str) -> list[dict[str, Any]]:
    try:
        lines = path(rel).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [json.loads(x) for x in lines if x.strip()]


def listing(rel: str) -> list[str]:
    p = path(rel)
    return sorted(c.name for c in p.iterdir()) if p.is_dir() else []
