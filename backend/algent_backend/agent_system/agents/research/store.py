"""
ProfileStore — the storage boundary for signal profiles.

Agents read/write profiles ONLY through this interface, so the backing store can
swap (JSON files now; Postgres/Supabase later) without touching agent code. This is
the seam that keeps data handling separate and makes the eventual database a drop-in
— a ``SupabaseProfileStore`` would implement the same three methods.

Profiles are durable assets (they outlive any single run, unlike run artifacts), so
they live in their own store dir, not under ``runs_data/``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

from .profile import SignalProfile

_STORE_ENV = "ALGENT_PROFILE_STORE"
_DEFAULT_DIR = "profile_store"


class ProfileStore(Protocol):
    """The one boundary profile data passes through."""

    def save(self, profile: SignalProfile) -> str: ...
    def get(self, profile_id: str) -> SignalProfile | None: ...
    def list_ids(self) -> list[str]: ...


def _safe(name: str) -> str:
    """A filesystem-safe filename stem for an id (ids use ':' which Windows rejects).

    Collisions are theoretically possible but unlikely for our id scheme; the future
    DB store removes the concern entirely. ``list_ids`` reads the authoritative id
    from file content, so the on-disk name never has to round-trip back to the id.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "profile"


class JsonProfileStore:
    """File-backed ProfileStore: one ``<safe-id>.json`` per profile under a base dir.

    The deliberately-simple default — durable and inspectable. Swap for a database
    implementation behind the ``ProfileStore`` protocol when serving/querying/accounts
    actually need one.
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._dir = Path(base_dir or os.environ.get(_STORE_ENV) or _DEFAULT_DIR)

    def save(self, profile: SignalProfile) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_safe(profile.id)}.json"
        path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def get(self, profile_id: str) -> SignalProfile | None:
        path = self._dir / f"{_safe(profile_id)}.json"
        if not path.exists():
            return None
        return SignalProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def list_ids(self) -> list[str]:
        if not self._dir.exists():
            return []
        ids = [self.get(p.stem) for p in self._dir.glob("*.json")]
        return sorted(p.id for p in ids if p is not None)
