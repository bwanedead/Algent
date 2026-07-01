"""
DraftStore — the storage boundary for article drafts.

A draft is a durable asset, lineage-linked to its treatment (and through it, the profile).
Same pattern as ProfileStore / TreatmentStore: JSON files now, swappable to a DB behind the
protocol. ``list_for_treatment`` is the lineage query.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Protocol

from .draft import ArticleDraft

_STORE_ENV = "ALGENT_DRAFT_STORE"
_DEFAULT_DIR = "draft_store"


class DraftStore(Protocol):
    """The one boundary draft data passes through."""

    def save(self, draft: ArticleDraft) -> str: ...
    def get(self, draft_id: str) -> ArticleDraft | None: ...
    def list_ids(self) -> list[str]: ...
    def list_for_treatment(self, treatment_id: str) -> list[ArticleDraft]: ...


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "draft"


class JsonDraftStore:
    """File-backed DraftStore: one ``<safe-id>.json`` per draft under a base dir."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._dir = Path(base_dir or os.environ.get(_STORE_ENV) or _DEFAULT_DIR)

    def save(self, draft: ArticleDraft) -> str:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{_safe(draft.id)}.json"
        path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def get(self, draft_id: str) -> ArticleDraft | None:
        path = self._dir / f"{_safe(draft_id)}.json"
        if not path.exists():
            return None
        return ArticleDraft.model_validate_json(path.read_text(encoding="utf-8"))

    def _all(self) -> list[ArticleDraft]:
        if not self._dir.exists():
            return []
        loaded = [self.get(p.stem) for p in self._dir.glob("*.json")]
        return [d for d in loaded if d is not None]

    def list_ids(self) -> list[str]:
        return sorted(d.id for d in self._all())

    def list_for_treatment(self, treatment_id: str) -> list[ArticleDraft]:
        kin = [d for d in self._all() if d.treatment_id == treatment_id]
        return sorted(kin, key=lambda d: (d.generated_at, d.revision), reverse=True)


def render_draft(draft: ArticleDraft) -> str:
    """A readable view of the draft — the piece, then a provenance footer."""
    out = [f"# {draft.title or '(untitled)'}"]
    if draft.standfirst:
        out += [f"*{draft.standfirst}*", ""]
    out += ["", draft.body.rstrip(), ""]
    out += [
        "---",
        f"_{draft.word_count} words · frame: {draft.frame or '?'} · "
        f"treatment {draft.treatment_id} · profile {draft.profile_id} (rev {draft.profile_revision})_",
    ]
    if draft.research_note:
        out += ["", f"**Drafting research:** {draft.research_note}"]
    if draft.cited_claim_ids:
        out += ["", f"**Cited claims:** {', '.join(draft.cited_claim_ids)}"]
    return "\n".join(out).rstrip() + "\n"
