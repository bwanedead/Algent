"""
TreatmentStore — the storage boundary for editorial treatments.

A treatment is a **durable asset**, not a run artifact: it is an abstraction layer derived
from a profile (the chosen vantage + the concept-molecule it makes legible), and it has
standalone knowledge-graph value — a profile can yield several treatments (different real
vantages), each a node lineage-linked to its parent. So treatments live in their own store
(JSON files now; Postgres/Supabase later), addressed by a stable content-derived id and
carrying ``profile_id`` so the lineage to the parent is always recoverable.

Agents read/write treatments ONLY through this interface, so the backing store can swap
without touching agent code — a ``SupabaseTreatmentStore`` would implement the same methods.
``list_for_profile`` is the lineage query: every treatment derived from a given profile.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

from .treatment import EditorialTreatment

_STORE_ENV = "ALGENT_TREATMENT_STORE"
_DEFAULT_DIR = "treatment_store"


class TreatmentStore(Protocol):
    """The one boundary treatment data passes through."""

    def save(self, treatment: EditorialTreatment) -> str: ...
    def get(self, treatment_id: str) -> EditorialTreatment | None: ...
    def list_ids(self) -> list[str]: ...
    def list_for_profile(self, profile_id: str) -> list[EditorialTreatment]: ...


def _safe(name: str) -> str:
    """A filesystem-safe filename stem for an id."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "treatment"


class JsonTreatmentStore:
    """File-backed TreatmentStore: one ``<safe-id>.json`` per treatment under a base dir.

    The deliberately-simple default — durable and inspectable. Swap for a database
    implementation behind the ``TreatmentStore`` protocol when querying the graph
    (treatments-by-profile, frames-by-entity) actually needs one.
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._dir = Path(base_dir or os.environ.get(_STORE_ENV) or _DEFAULT_DIR)

    def save(self, treatment: EditorialTreatment) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_safe(treatment.id)}.json"
        path.write_text(treatment.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def get(self, treatment_id: str) -> EditorialTreatment | None:
        path = self._dir / f"{_safe(treatment_id)}.json"
        if not path.exists():
            return None
        return EditorialTreatment.model_validate_json(path.read_text(encoding="utf-8"))

    def _all(self) -> list[EditorialTreatment]:
        if not self._dir.exists():
            return []
        loaded = [self.get(p.stem) for p in self._dir.glob("*.json")]
        return [t for t in loaded if t is not None]

    def list_ids(self) -> list[str]:
        return sorted(t.id for t in self._all())

    def list_for_profile(self, profile_id: str) -> list[EditorialTreatment]:
        """Lineage query: every treatment derived from this profile (newest revision first)."""
        kin = [t for t in self._all() if t.profile_id == profile_id]
        return sorted(kin, key=lambda t: (t.generated_at, t.revision), reverse=True)
