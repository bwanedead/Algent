"""
The watch — the one object the stream service holds: the profile book, and (once per ``DETECT_SECONDS``) the detector pass over it.

    watch.identity(...)      called by the vessel board for broadcast identity (static messages, names on position messages)
    watch.cycle(board, ...)  called once a cycle: folds the board's rows into the book, prunes, and runs due detector passes
    watch.persist_due(now)   True when the profile book should be written; ``document()`` is built on the loop thread

Everything here is derived from AIS the service already hears; nothing is fetched. Failure is local: a broken detector pass is recorded
and the next cycle runs again; it never costs the stream a snapshot.
"""

from __future__ import annotations

from typing import Any

from . import flags, store
from .profile import ProfileBook


class Watch:
    def __init__(self, book: ProfileBook | None = None) -> None:
        self.book = book or ProfileBook()
        self.last_persist = 0.0

    @classmethod
    def load(cls) -> "Watch":
        return cls(ProfileBook.load(store.profiles_path()))

    # ── input ──────────────────────────────────────────────────────────────────────────────────
    def identity(self, mmsi: int, name: Any, imo: Any, ship_type: Any, ts: float) -> None:
        self.book.identity(mmsi, name, imo, ship_type, ts)

    def cycle(self, board: Any, now: float) -> dict[str, Any]:
        """One cycle: fold the board's rows into the book and prune it. Returns a small account."""
        n = self.book.observe(((m, r[0], r[1], r[3], r[4]) for m, r in board.v.items()), now)
        removed = self.book.prune(now)
        return {"updated": n, "profiles": len(self.book.profiles), "expired": removed}

    # ── disk ───────────────────────────────────────────────────────────────────────────────────
    def persist_due(self, now: float) -> bool:
        return now - self.last_persist >= flags.PERSIST_SECONDS

    def document(self, now: float) -> dict[str, Any]:
        self.last_persist = now
        return self.book.document()
