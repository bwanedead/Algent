"""
ArtifactRef — serializable pointer to one durable run output.

Unlike ``AgentSpec``/``ToolSpec`` (in-process recipes carrying callables), an
artifact reference crosses process and storage boundaries: it lands in
``result.json``, the run ledger, and later GraphOS projections. That is why it
is a Pydantic model, not a dataclass.
"""

from __future__ import annotations

from pydantic import BaseModel


class ArtifactRef(BaseModel):
    """Pointer to a durable output written during a run."""

    artifact_id: str
    run_id: str
    name: str
    # Loose content-kind tag ("markdown", "json", "text", ...). Open string on
    # purpose — new kinds appear organically; consumers must tolerate unknowns.
    kind: str
    # Path relative to the run's artifacts directory (portable across machines).
    relative_path: str
    created_at: str
    size_bytes: int
