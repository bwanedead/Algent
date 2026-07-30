"""
Rake stage configuration — the scout's model, channels, and budgets.

Not a registered runnable agent: rake is a *stage* the synthesis run invokes on its
t0 pool before the synthesis model sees it (see ``synthesis/loop.py``). These
constants keep the tuning in one place, mirroring an ``AgentSpec``'s knobs.
"""

from __future__ import annotations

from algent_backend.agent_system.foundation.models import openai_spec
from algent_backend.agent_system.tools.sourcing.search import policy
from algent_backend.agent_system.tools.sourcing.search.research import WEB_SEARCH_TOOL_ID

TOOL_IDS = (WEB_SEARCH_TOOL_ID,)
# Low effort — high-volume surface sieve, not deep work. Same house model as the
# rest of the OpenAI rail; effort is what keeps this stage cheap.
RAKE_MODEL = openai_spec(reasoning_effort="low", temperature=0.2, streaming=True)
# Free channels only: a fence-sitter check is a free read/search; rake never pays.
RAKE_CHANNELS = (policy.KEYWORD, policy.SEMANTIC, policy.READ)
RAKE_PAID_BUDGET = 0
# Items per chunk handed to one scout pass. Kept small because each keeper may also
# free-read its source to ground it — small chunks keep every pass within the agent's
# step budget and the reads focused.
RAKE_CHUNK_SIZE = 12
# Hard ceiling on the rake stage's estimated spend. Reads are free; this just bounds
# tokens spent summarizing them.
RAKE_COST_CAP_USD = 0.60
