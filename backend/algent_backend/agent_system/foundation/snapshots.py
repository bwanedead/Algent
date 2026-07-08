"""
Source snapshots — per-run capture of what a source actually said when we read it.

The integrity counterpart to the model's judgment: the MODEL builds the claim/source
ledgers, but it must NOT be trusted to hash content. So the read path records, per
source URL, a content hash + excerpt + timestamp into this per-run collector (a
ContextVar, like the cost meter). After the run, the harness attaches these snapshots
to the matching ``SourceArtifact``s — deterministic, tamper-evident evidence that
proves what a source said at read-time.

Zero overhead and isolated: nothing is recorded unless a run wraps itself in
``scoped()`` (so the shared default store is never mutated).
"""

from __future__ import annotations

import contextvars
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

# The captured excerpt is tamper-evidence AND the corpus the citation harness verifies figures
# against (a figure a source really carried is verified-at-capture). News ledes carry the key
# numbers, so capture enough to cover them — not the whole page (that would bloat the profile).
_EXCERPT_CHARS = 1200

_active: contextvars.ContextVar[bool] = contextvars.ContextVar("snapshots_active", default=False)
# Default {} is never mutated: record() no-ops unless active, and scoped() always
# installs a fresh dict before activating.
_store: contextvars.ContextVar[dict[str, dict[str, Any]]] = contextvars.ContextVar(
    "snapshots_store", default={}  # noqa: B039 — never mutated; scoped() installs a fresh dict
)


def is_active() -> bool:
    return _active.get()


def record(url: str, content: str) -> None:
    """Capture a source's content at read-time (first read of a URL wins)."""
    if not _active.get() or not url or not content:
        return
    store = _store.get()
    if url in store:
        return
    store[url] = {
        "content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "excerpt": content.strip()[:_EXCERPT_CHARS],
        "captured_at": datetime.now(UTC).isoformat(),
    }


def collected() -> dict[str, dict[str, Any]]:
    """The snapshots captured this run, keyed by source URL."""
    return dict(_store.get())


@contextmanager
def scoped() -> Iterator[None]:
    """Collect source snapshots for one run; resets afterwards."""
    tokens = (_active.set(True), _store.set({}))
    try:
        yield
    finally:
        _active.reset(tokens[0])
        _store.reset(tokens[1])
