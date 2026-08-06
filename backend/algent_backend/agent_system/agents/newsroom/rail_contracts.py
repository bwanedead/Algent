"""
Full-rail report — the one document a raw-discovery-to-article run produces.

The rail chains the proven stages (discovery synthesis -> routing -> profile -> profile gauntlet ->
editorial pipeline) under a single run, so a run starts from nothing but the t0 pool (plus any
backfed leads) and ends at a finished, receipted article. This report is the human-approval
surface's summary: how far the rail got, what it promoted, whether the piece is publishable, and
what the whole thing cost.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

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
    # Launch mode: "fresh" runs t0+synthesis; "reused" skips them and re-routes a prior portfolio
    # (still cooldown-guarded) so a second on-deck vector can be tried without re-paying t0.
    portfolio_source: str = "fresh"     # "fresh" | "reused" | "paused"
    source_run_id: str = ""             # prior run id when portfolio_source=reused (observability)
    # Measured, not inferred: how often any stage actually reached for live X. Zero across a run
    # means the source class is wired but unused — which is what two doctrine passes failed to fix.
    x_searches: int = 0
    # DISCOVERY OBSERVABILITY — where the news actually came from. `pool_by_channel` is what each
    # source contributed; `promoted_from` is which channel(s) fed the story we ACTUALLY ran. The
    # ratio between them is the overfit signal: a channel that supplies a quarter of the pool but
    # every promoted story is steering the newsroom, and that is invisible without this.
    pool_by_channel: dict[str, int] = Field(default_factory=dict)
    promoted_from: dict[str, int] = Field(default_factory=dict)
    # ── promotion ──
    selected_vector_id: str = ""
    selected_vector_title: str = ""
    # ── research ──
    profile_id: str = ""
    gauntlet_verdict: str = ""          # profile gauntlet's final verdict
    # Disposition when the rail stops short of a full article (held research lead).
    # Empty when editorial ran; otherwise watch | needs_verification | unsound | held.
    disposition: str = ""
    # ── editorial ──
    article_status: str = ""            # publishable | needs_hedging | blocked | needs_revision
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
    total_usd: float = 0.0              # settled spend under the article ledger
    soft_cap_usd: float = 1.0
    hard_cap_usd: float = 3.0
    budget_mode: str = "normal"         # normal | slim_finish | hard_stop
    soft_cap_crossed: bool = False
    soft_crossed_at_stage: str = ""
    hard_stop: bool = False
    hard_stop_stage: str = ""
    cost_by_stage: dict[str, float] = Field(default_factory=dict)
    cost_by_op: dict[str, float] = Field(default_factory=dict)
    skipped_operations: list[dict[str, str]] = Field(default_factory=list)
    refused_operations: list[dict[str, str]] = Field(default_factory=list)
    note: str = ""
    generated_at: str = ""
