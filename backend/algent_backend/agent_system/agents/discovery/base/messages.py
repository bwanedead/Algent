"""
Discovery task messages — the per-run user payload, distinct from the system
prompt.

The system prompt (``prompts.py``) is the discovery agent's fixed identity. This
module owns the *task message*: the standing directive for one run plus the
optional query seed a caller injects. A goal narrows the survey; its absence
means an open sweep. Assembled with ``stitch_message`` so the seed segment is
simply present or not — the query seed is per-run input, never part of identity.
"""

from __future__ import annotations

from algent_backend.agent_system.prompting import stitch_message

# The query seed: the open-survey default when no goal is given. A caller-provided
# goal is framed by ``goal_seed``. Either way this is per-run input, not identity.
OPEN_SURVEY_SEED = (
    "Survey broadly for notable, interesting, or significant items that could be "
    "worth deeper coverage."
)


def goal_seed(goal: str) -> str:
    """Frame a caller-provided goal as the run's query seed."""
    return f"Focus your discovery on this goal: {goal}"


def _task_directive(cap: int) -> str:
    return (
        "Use your discovery tools to look at what is actually being reported, "
        f"then return up to {cap} candidate topics worth deeper investigation. "
        "Be selective and ground each candidate in sources you found. Returning "
        "fewer (or none) is fine if little clears the bar."
    )


def build_task_message(goal: str | None, cap: int) -> str:
    """Stitch the run's task message: the query seed (goal or open survey) then
    the standing directive. The seed segment is conditional on ``goal``.
    """
    seed = goal_seed(goal) if goal else OPEN_SURVEY_SEED
    return stitch_message(seed, _task_directive(cap))
