"""
Editorial pipeline — the article side: profile -> treatment -> (review) -> draft -> (review).

The planning stage lives here now: the EditorialTreatment contract and the editorial_planner
agent that produces it. Later stages (treatment reviewer, drafter, draft reviewer) join as
they are built. Re-exports the contract for ergonomic imports.
"""

from __future__ import annotations

from .treatment import (
    EditorialTreatment,
    FrameOption,
    PerspectiveTake,
    TreatmentConcept,
)

__all__ = [
    "EditorialTreatment",
    "FrameOption",
    "PerspectiveTake",
    "TreatmentConcept",
]
