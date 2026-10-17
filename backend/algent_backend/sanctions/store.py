"""
Sanctions store on disk — an append-only event log plus one current snapshot per source.

    <root>/events.jsonl          one SanctionsEvent per line, never rewritten (a repeated id is ignored)
    <root>/snapshots/<src>.json  the source's list as of the last good fetch (the diff's "before"; replaced atomically)
    <root>/status.json           per source: last good fetch, last error, entry count, events found
    <root>/published.json        how many event lines the site database already has

Root: ``ALGENT_SANCTIONS_STORE`` or ``sanctions_store``. The log is the record; snapshots are only the working memory a diff needs.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .contracts import Entry, SanctionsEvent

_ENV = "ALGENT_SANCTIONS_STORE"


def root() -> Path:
    return Path(os.environ.get(_ENV) or "sanctions_store")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


# -- snapshots -----------------------------------------------------------------------------------
def load_snapshot(source: str) -> dict[str, Entry] | None:
    """The source's list as of the last good fetch; None before the first one."""
    try:
        rows = json.loads((root() / "snapshots" / f"{source}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {e.ref: e for e in (Entry.model_validate(r) for r in rows)}


def save_snapshot(source: str, entries: dict[str, Entry]) -> None:
    _write(root() / "snapshots" / f"{source}.json", json.dumps([e.model_dump(exclude_defaults=False) for e in entries.values()], ensure_ascii=False, separators=(",", ":")))


# -- events --------------------------------------------------------------------------------------
def _lines() -> list[str]:
    try:
        return [x for x in (root() / "events.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return []


def events() -> list[SanctionsEvent]:
    out = []
    for line in _lines():
        try:
            out.append(SanctionsEvent.model_validate_json(line))
        except ValueError:
            continue                                        # a torn line must not hide the rest
    return out


def append_events(new: list[SanctionsEvent]) -> int:
    """Append the events whose id is not on file; returns how many were written."""
    known = {e.id for e in events()}
    fresh = [e for e in new if e.id not in known and not known.add(e.id)]
    if fresh:
        path = root() / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(e.model_dump_json() for e in fresh) + "\n")
    return len(fresh)


# -- status / publish watermark ------------------------------------------------------------------
def load_status() -> dict[str, dict]:
    try:
        return json.loads((root() / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_status(source: str, **fields: object) -> None:
    st = load_status()
    st[source] = {**st.get(source, {}), **fields}
    _write(root() / "status.json", json.dumps(st, indent=1, ensure_ascii=False))


def published_count() -> int:
    try:
        return int(json.loads((root() / "published.json").read_text(encoding="utf-8")).get("events", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def save_published(n: int) -> None:
    _write(root() / "published.json", json.dumps({"events": n}))


def event_lines_after(n: int) -> list[SanctionsEvent]:
    out = []
    for line in _lines()[n:]:
        try:
            out.append(SanctionsEvent.model_validate_json(line))
        except ValueError:
            continue
    return out


def line_count() -> int:
    return len(_lines())
