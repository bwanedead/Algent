"""
The watch — the one object the stream service holds: the profile book, and (once per ``DETECT_SECONDS``) the detector pass over it.

    watch.identity(...)      called by the vessel board for broadcast identity (static messages, names on position messages)
    watch.cycle(board, now)  called once a cycle: folds the board's rows into the book, prunes, and runs a due detector pass
    watch.persist_due(now)   True when the profile book should be written; ``document()`` is built on the loop thread

Everything here is derived from AIS the service already hears; nothing is fetched. Failure is local: a broken detector is recorded and the
next pass runs again. A restart after the stream was down marks a blind window (``blind_until``): silences that began inside it say nothing.
"""

from __future__ import annotations

from typing import Any

from . import flags, sites, store
from .contracts import BehaviourEvent
from .detect import gap, identity, loiter, sanctioned, sts
from .detect.common import Context, Fresh
from .profile import ProfileBook

#: A stream that was not cycling for this long was blind, not the sea quiet.
BLIND_S = 600
_RELATED_BOOST = {"sanctioned": 0.2, "identity": 0.1, "ais_gap": 0.1, "sts": 0.1, "loiter": 0.1}


class Watch:
    def __init__(self, book: ProfileBook | None = None, state: dict[str, Any] | None = None, excl: sites.Exclusion | None = None) -> None:
        self.book = book or ProfileBook()
        self.state: dict[str, Any] = state if state is not None else {}
        self.excl = excl
        self.sanctions: Any = None
        self.last_persist = 0.0
        self.last_detect = 0.0
        self.last_account: dict[str, Any] = {}

    @classmethod
    def load(cls) -> "Watch":
        return cls(ProfileBook.load(store.profiles_path()), store.read_state())

    # ── input ──────────────────────────────────────────────────────────────────────────────────
    def identity(self, mmsi: int, name: Any, imo: Any, ship_type: Any, ts: float) -> None:
        self.book.identity(mmsi, name, imo, ship_type, ts)

    def cycle(self, board: Any, now: float) -> dict[str, Any]:
        """One cycle: fold the board's rows into the book, prune it, and run the detector pass when one is due."""
        last = float(self.state.get("last_cycle", 0.0))
        if last and now - last > BLIND_S:
            self.state["blind_until"] = now
        self.state["last_cycle"] = now
        n = self.book.observe(((m, r[0], r[1], r[3], r[4]) for m, r in board.v.items()), now)
        removed = self.book.prune(now)
        out: dict[str, Any] = {"updated": n, "profiles": len(self.book.profiles), "expired": removed}
        if now - self.last_detect >= flags.DETECT_SECONDS:
            self.last_detect = now
            out["detect"] = self.last_account = self.detect(board, now)
        return out

    # ── the pass ───────────────────────────────────────────────────────────────────────────────
    def context(self, board: Any, now: float) -> Context:
        if self.excl is None:
            self.excl = sites.from_environment()
        self.sanctions = sanctioned.refreshed(self.sanctions, now)
        fresh = [Fresh(m, r[0], r[1], r[3], r[4], (board.static.get(m) or [0])[0], board.name.get(m, "")) for m, r in board.v.items()
                 if r[4] >= now - flags.FRESH_S]
        return Context(now, self.book, board.coverage.seen, fresh, self.excl, float(self.state.get("blind_until", 0.0)), self.sanctions)

    def detect(self, board: Any, now: float) -> dict[str, Any]:
        ctx = self.context(board, now)
        current = store.read_current()
        found: list[BehaviourEvent] = []
        errors: dict[str, str] = {}
        for name, run in (("gap", lambda: gap.detect(ctx, current)), ("sts", lambda: sts.detect(ctx, self.state)),
                          ("identity", lambda: identity.detect(ctx, current)), ("sanctioned", lambda: sanctioned.detect(ctx, current)),
                          ("loiter", lambda: loiter.detect(ctx, self.state))):
            try:
                found += run()
            except Exception as exc:  # noqa: BLE001 - one broken detector must not silence the rest
                errors[name] = f"{type(exc).__name__}: {str(exc)[:120]}"
        found = link_related(found, current, now)
        res = store.upsert(found, now)
        store.write_state(self.state)
        return {**res, "found": len(found), "screened": ctx.notes, **({"errors": errors} if errors else {})}

    # ── disk ───────────────────────────────────────────────────────────────────────────────────
    def persist_due(self, now: float) -> bool:
        return now - self.last_persist >= flags.PERSIST_SECONDS

    def document(self, now: float) -> dict[str, Any]:
        self.last_persist = now
        return self.book.document()


def link_related(found: list[BehaviourEvent], current: dict[str, BehaviourEvent], now: float) -> list[BehaviourEvent]:
    """A vessel with more than one kind of flag is worth more than the sum: raise each event's confidence by what else is on record for the
    same MMSI (a sanctions match most), and say so in ``detail.related``. Judged afresh each pass, so it never ratchets."""
    kinds: dict[int, set[str]] = {}
    for e in [*current.values(), *found]:
        for m in (e.mmsi, e.mmsi2):
            if m:
                kinds.setdefault(m, set()).add(e.kind)
    out = []
    for e in found:
        rel = set().union(*(kinds.get(m, set()) for m in (e.mmsi, e.mmsi2) if m)) - {e.kind}
        base = float(e.detail.get("base_conf", e.confidence))
        boost = max((_RELATED_BOOST[k] for k in rel), default=0.0)
        out.append(e.model_copy(update={"confidence": round(min(1.0, base + boost), 3),
                                        "detail": {**e.detail, "base_conf": base, **({"related": sorted(rel)} if rel else {})}}))
    return out
