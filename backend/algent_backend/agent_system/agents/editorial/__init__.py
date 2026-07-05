"""
Editorial pipeline — the article side: profile -> treatment -> (review) -> draft -> (review).

The planning stage lives here now: the EditorialTreatment contract and the editorial_planner
agent that produces it. Later stages (treatment reviewer, drafter, draft reviewer) join as
they are built. Re-exports the contract for ergonomic imports.
"""

from __future__ import annotations

from .citations import CitationReport, check_citations
from .draft import ArticleDraft, DraftPayload
from .draft_gauntlet_contracts import DraftingGauntletReport
from .gauntlet_contracts import PlanningGauntletReport
from .review_contracts import TreatmentFinding, TreatmentReview
from .treatment import (
    EditorialTreatment,
    FrameOption,
    PerspectiveTake,
    TreatmentConcept,
)

__all__ = [
    "ArticleDraft",
    "CitationReport",
    "DraftPayload",
    "DraftingGauntletReport",
    "check_citations",
    "EditorialTreatment",
    "FrameOption",
    "PerspectiveTake",
    "PlanningGauntletReport",
    "TreatmentConcept",
    "TreatmentFinding",
    "TreatmentReview",
]
