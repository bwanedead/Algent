"""
Ohmega Pulse — persistent, auditable belief states that compound.

Public surface: the contracts, the store, and the projection. Consumers (the rail hook, the
reassessment command, the site, the agent API) depend on these and on nothing inside.
Design: docs/architecture/pulse-system.md.
"""

from .contracts import (
    BANDS,
    Anchor,
    Confidence,
    Influence,
    Pulse,
    PulseDefinition,
    Situation,
    Source,
    Watch,
    band_of,
    influence_key,
)
from .projection import RECONCILE_GAP, PulseState, project
from .store import DuplicateInfluence, PulseStore

__all__ = [
    "BANDS", "Anchor", "Confidence", "DuplicateInfluence", "Influence", "Pulse",
    "PulseDefinition", "PulseState", "PulseStore", "RECONCILE_GAP", "Situation", "Source",
    "Watch", "band_of", "influence_key", "project",
]
