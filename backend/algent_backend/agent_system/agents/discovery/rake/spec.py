"""
Rake stage configuration — the scout's model, channels, and budgets.

Not a registered runnable agent: rake is a *stage* the synthesis run invokes on its
t0 pool before the synthesis model sees it (see ``synthesis/loop.py``). These
constants keep the tuning in one place, mirroring an ``AgentSpec``'s knobs.
"""

from __future__ import annotations

from algent_backend.agent_system.foundation.models import house_spec
from algent_backend.agent_system.tools.sourcing.search import policy

#: No tools. The scout used to free-read the source of every keeper to ground it, which made the
#: rake 64 of a 72-minute menu build — ~90 sequential page fetches, many of them failing slowly —
#: to drop 5 items of 107. The only items that need their page are the GDELT theme-coded ones,
#: and those are grounded in code before the scout runs (``loop._ground_thin``).
TOOL_IDS: tuple[str, ...] = ()
# Low effort — high-volume surface sieve, not deep work. Same house model as the
# rest of the OpenAI rail; effort is what keeps this stage cheap.
RAKE_MODEL = house_spec(reasoning_effort="low", temperature=0.2, streaming=True)
# Free channels only: a fence-sitter check is a free read/search; rake never pays.
RAKE_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ)
RAKE_PAID_BUDGET = 0
# Items per chunk handed to one scout pass. With no reads, a chunk is one short structured reply
# of verdicts, so the chunk is sized to keep that reply comfortably small, not to ration reads.
RAKE_CHUNK_SIZE = 40
# Hard ceiling on the rake stage's estimated spend. Reads are free; this just bounds
# tokens spent summarizing them.
RAKE_COST_CAP_USD = 0.60
