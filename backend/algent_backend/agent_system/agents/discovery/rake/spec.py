"""
Rake stage configuration — the nano scout's model, channels, and budgets.

Not a registered runnable agent: rake is a *stage* the synthesis run invokes on its
t0 pool before the synthesis model sees it (see ``synthesis/loop.py``). These
constants keep the tuning in one place, mirroring an ``AgentSpec``'s knobs.
"""

from __future__ import annotations

from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
# Cheapest tier — this is a high-volume surface-level sieve, not deep work.
RAKE_MODEL = ModelSpec(
    provider="openai",
    model="gpt-5.4-nano",
    temperature=0.2,
    extra={"streaming": True, "stream_usage": True},
)
# Free channels only: a fence-sitter check is a free read/search; rake never pays.
RAKE_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ)
RAKE_PAID_BUDGET = 0
# Items per chunk handed to one scout pass. Small keeps each pass focused & cheap.
RAKE_CHUNK_SIZE = 25
# Hard ceiling on the rake stage's estimated spend (nano tokens + free calls ~ $0).
RAKE_COST_CAP_USD = 0.30
