"""
ProfileStore — the storage boundary for signal profiles.

Agents read/write profiles ONLY through this interface, so the backing store can
swap (JSON files now; Postgres/Supabase later) without touching agent code. This is
the seam that keeps data handling separate and makes the eventual database a drop-in
— a ``SupabaseProfileStore`` would implement the same three methods.

Profiles are durable assets (they outlive any single run, unlike run artifacts), so
they live in their own store dir, not under ``runs_data/``.

Nothing written here is ever lost
---------------------------------
The store used to be one file per id, overwritten on every save. Ids were not unique enough —
every brief became ``prof_unknown`` and every menu numbered its vectors from ``v01`` again — so
sixteen stories' research was silently saved over by later, unrelated stories. The profiles
are meant to accumulate into the newsroom's knowledge base; a store that forgets defeats the
point of having one. So, three rules:

1. **History is append-only.** Every save also writes ``_history/<id>/<rev>__<time>.json``.
   The current file is a convenience view; the history is the record.
2. **A different story never takes an existing slot.** If a save would replace a profile about
   something else, it is written under a new id instead, and the collision is logged to
   ``_collisions.jsonl`` so it is visible rather than silent.
3. **The pages read are kept** beside the profile (``<id>.reads.jsonl``) — the raw research,
   which run folders do not keep past five newer runs.
4. **A failed attempt never replaces a complete profile.** A result that is not ``is_complete``
   (no sourced claim: a run cut short) is saved aside under ``_rejected/<id>/`` with the reason in
   ``_rejections.jsonl``, and the good version stays current. (A streaming schema bug once saved
   empty profiles over the day's finished research; the next rerun then paid for it again.)
5. **Reuse heals.** ``current_complete`` returns the current profile if complete, else restores
   the newest complete version from history as current (logged in ``_restorations.jsonl``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .profile import SignalProfile

_STORE_ENV = "ALGENT_PROFILE_STORE"
_DEFAULT_DIR = "profile_store"


class ProfileStore(Protocol):
    """The one boundary profile data passes through."""

    def save(self, profile: SignalProfile) -> str: ...
    def save_reads(self, profile_id: str, reads_file: Path) -> str | None: ...
    def get(self, profile_id: str) -> SignalProfile | None: ...
    def list_ids(self) -> list[str]: ...


def _safe(name: str) -> str:
    """A filesystem-safe filename stem for an id (ids use ':' which Windows rejects)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "profile"


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def profile_shape(profile: SignalProfile) -> dict:
    """How much a profile holds, for logs and reports."""
    return {"revision": profile.revision, "generated_at": profile.generated_at, "claims": len(profile.claim_ledger),
            "sourced_claims": sum(1 for c in profile.claim_ledger if c.supported_by),
            "sources": len(profile.source_ledger)}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def same_story(a: SignalProfile, b: SignalProfile) -> bool:
    """Whether two profiles are revisions of one story rather than two stories sharing an id.

    Same parent vector, or same title, or any source in common. Deliberately generous: a false
    "same" is an ordinary overwrite that history still preserves, while a false "different"
    only costs a duplicate slot.
    """
    if a.parent_vector_id and a.parent_vector_id == b.parent_vector_id:
        return True
    if _norm(a.title) and _norm(a.title) == _norm(b.title):
        return True
    urls_a = {s.url for s in a.source_ledger if s.url}
    return bool(urls_a & {s.url for s in b.source_ledger if s.url})


class JsonProfileStore:
    """File-backed ProfileStore: ``<safe-id>.json`` per profile, plus an append-only history.

    Swap for a database implementation behind the ``ProfileStore`` protocol when
    serving/querying/accounts actually need one.
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._dir = Path(base_dir or os.environ.get(_STORE_ENV) or _DEFAULT_DIR)

    @property
    def root(self) -> Path:
        return self._dir

    def save(self, profile: SignalProfile) -> str:
        """Save a profile; returns the path of the CURRENT file for its id (which, when the save was
        set aside as a failed attempt, is still the good version)."""
        self._dir.mkdir(parents=True, exist_ok=True)
        profile = self._claim_slot(profile)
        existing = self.get(profile.id)
        if existing is not None and existing.is_complete and not profile.is_complete:
            self._set_aside(profile, existing)
            return str(self._path(profile.id))
        return self._write(profile)

    def _path(self, profile_id: str) -> Path:
        return self._dir / f"{_safe(profile_id)}.json"

    def _write(self, profile: SignalProfile) -> str:
        blob = profile.model_dump_json(indent=2)
        path = self._path(profile.id)
        path.write_text(blob, encoding="utf-8")
        hist = self._dir / "_history" / _safe(profile.id)
        hist.mkdir(parents=True, exist_ok=True)
        (hist / f"r{profile.revision:03d}__{_stamp()}.json").write_text(blob, encoding="utf-8")
        return str(path)

    def _log(self, name: str, entry: dict) -> None:
        with (self._dir / name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": datetime.now(UTC).isoformat(), **entry}, ensure_ascii=False) + "\n")

    def _set_aside(self, profile: SignalProfile, kept: SignalProfile) -> None:
        """Keep a failed attempt where it can be inspected, without letting it replace ``kept``."""
        aside = self._dir / "_rejected" / _safe(profile.id)
        aside.mkdir(parents=True, exist_ok=True)
        name = f"r{profile.revision:03d}__{_stamp()}.json"
        (aside / name).write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        self._log("_rejections.jsonl", {
            "id": profile.id, "saved_as": f"_rejected/{_safe(profile.id)}/{name}",
            "reason": "not complete (no sourced claim); would have replaced a complete profile",
            "incoming": profile_shape(profile), "kept": profile_shape(kept),
        })

    def _claim_slot(self, profile: SignalProfile) -> SignalProfile:
        """The id this profile may be saved under — never one that belongs to another story."""
        existing = self.get(profile.id)
        if existing is None or same_story(existing, profile):
            return profile
        new_id = f"{profile.id}__{hashlib.sha1(_norm(profile.title).encode()).hexdigest()[:8]}"
        with (self._dir / "_collisions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": datetime.now(UTC).isoformat(), "id": profile.id, "saved_as": new_id,
                "kept": existing.title, "incoming": profile.title,
            }, ensure_ascii=False) + "\n")
        return profile.model_copy(update={"id": new_id})

    def save_reads(self, profile_id: str, reads_file: Path) -> str | None:
        """Keep the full text of every page this story's research read, beside its profile."""
        if not reads_file.exists():
            return None
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_safe(profile_id)}.reads.jsonl"
        path.write_bytes(reads_file.read_bytes())
        return str(path)

    def get(self, profile_id: str) -> SignalProfile | None:
        path = self._dir / f"{_safe(profile_id)}.json"
        if not path.exists():
            return None
        return SignalProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def list_ids(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.id for p in self.iter_profiles())

    def iter_profiles(self):
        """Every current profile, each file read once (the corpus index and ``list_ids`` share this)."""
        if not self._dir.exists():
            return
        for path in sorted(self._dir.glob("*.json")):
            profile = self.get(path.stem)
            if profile is not None:
                yield profile

    def history(self, profile_id: str) -> list[Path]:
        hist = self._dir / "_history" / _safe(profile_id)
        return sorted(hist.glob("*.json")) if hist.exists() else []

    def newest_complete(self, profile_id: str) -> tuple[Path, SignalProfile] | None:
        """The most recently saved COMPLETE version of this id in history (by save time, not revision:
        a rerun starts again at revision 1), or None."""
        for path in sorted(self.history(profile_id), key=lambda p: p.stem.split("__", 1)[-1], reverse=True):
            try:
                found = SignalProfile.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - an unreadable version is simply not a candidate
                continue
            if found.is_complete:
                return path, found
        return None

    def current_complete(self, profile_id: str) -> SignalProfile | None:
        """The profile for this id if a complete one exists anywhere. When the current version is not
        complete but history holds a complete one, that version is restored as current first."""
        current = self.get(profile_id)
        if current is not None and current.is_complete:
            return current
        best = self.newest_complete(profile_id)
        if best is None:
            return None
        return self.restore(profile_id, best[0], replaced=current)

    def restore(self, profile_id: str, version: Path, *, replaced: SignalProfile | None = None) -> SignalProfile:
        """Make a history version current again, and say so in ``_restorations.jsonl``."""
        restored = SignalProfile.model_validate_json(version.read_text(encoding="utf-8"))
        self._write(restored)
        self._log("_restorations.jsonl", {
            "id": profile_id, "restored_from": version.name, "restored": profile_shape(restored),
            "replaced": profile_shape(replaced) if replaced is not None else None,
        })
        return restored
