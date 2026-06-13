"""
General discovery — the specialty prompt layer, plus the composed system prompt.

This is the broadest discovery specialty: it sweeps for anything notable, and
can be narrowed at runtime by an injected goal (handled in the loop's task
message, not here). ``SYSTEM_PROMPT`` is the assembled identity: universal base
-> discovery class -> this specialty. A runtime goal is an additional task-level
layer, kept out of the fixed system prompt.
"""

from __future__ import annotations

from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

from ..base.prompts import DISCOVERY_BASE

GENERAL_DISCOVERY = (
    "You are the general discovery agent. Sweep broadly: surface items that are "
    "interesting, surprising, consequential, or under-covered — not only breaking "
    "news. Favor variety and non-obvious finds over a narrow beat. If given a "
    "specific goal, concentrate your survey there instead of sweeping broadly."
)

SYSTEM_PROMPT = compose_system_prompt(
    UNIVERSAL_AGENT_BASE,
    DISCOVERY_BASE,
    GENERAL_DISCOVERY,
)
