"""
Full-rail report — the one document a raw-discovery-to-article run produces.

The rail chains the proven stages (discovery synthesis -> routing -> profile -> profile gauntlet ->
editorial pipeline) under a single run, so a run starts from nothing but the t0 pool (plus any
backfed leads) and ends at a finished, receipted article. This report is the human-approval
surface's summary: how far the rail got, what it promoted, whether the piece is publishable, and
what the whole thing cost.
"""

from __future__ import annotations

from pydantic import BaseModel

# How far the rail progressed — each stage can legitimately be the end (no promotable vector is a
# valid, non-error outcome, just as a still-needs_revision treatment is downstream).
RailStage = str  # "backfeed" | "synthesis" | "routing" | "profile" | "gauntlet" | "editorial" | "complete"


class NewsroomRailReport(BaseModel):
    """What one full-rail run produced, end to end."""

    stage_reached: RailStage = "synthesis"
    # ── discovery ──
    pool_items: int = 0                 # t0 items considered (incl. any backfed leads)
    backfeed_leads_injected: int = 0    # damped open leads merged into the pool (the loop closing)
    vector_count: int = 0               # t1 vectors synthesized
    # ── promotion ──
    selected_vector_id: str = ""
    selected_vector_title: str = ""
    # ── research ──
    profile_id: str = ""
    gauntlet_verdict: str = ""          # profile gauntlet's final verdict
    # ── editorial ──
    article_status: str = ""            # publishable | needs_hedging | blocked
    article_title: str = ""
    analytics_produced: int = 0
    # ── distribution ──
    # The rail publishes itself: a piece that earns `publishable` goes live by virtue of the
    # pipeline, not because someone ran a command. `publish_action` records what actually happened
    # (published | staged | held | refused | ...) so the ledger tells the whole story of the run.
    published: bool = False
    published_slug: str = ""
    publish_action: str = ""
    # ── accounting ──
    total_usd: float = 0.0              # summed est. spend across every stage that surfaced it
    note: str = ""
    generated_at: str = ""
