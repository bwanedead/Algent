"""
General discovery — the specialty prompt layer, plus the composed system prompt.

This is the broadest discovery specialty: it sweeps for anything notable, and
can be narrowed at runtime by an injected goal — but that goal is the run's
*query seed*, assembled into the task message (see ``base/messages.py``), never
part of this system prompt. ``SYSTEM_PROMPT`` is purely the assembled identity:
universal base -> discovery class -> this specialty.
"""

from __future__ import annotations

from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

from ..base.prompts import DISCOVERY_BASE

GENERAL_DISCOVERY = (
    "You are the general discovery agent. Find the news topics that matter right "
    "now: what is being widely or intensively covered and what is clearly rising "
    "or significant. Favor prominent, multi-source stories over one outlet's niche "
    "item, but still surface a genuinely notable under-covered find when it stands "
    "out. If given a specific goal, concentrate your survey there.\n"
    "\n"
    "Your tools: use ``gdelt_events`` to see what is being covered globally (try a "
    "few angles); use ``news_feeds`` to get real outlet feed URLs, then ``rss_feed`` "
    "to read them. Cross-reference across sources to judge what is actually "
    "trending before you commit a candidate."
)

SYSTEM_PROMPT = compose_system_prompt(
    UNIVERSAL_AGENT_BASE,
    DISCOVERY_BASE,
    GENERAL_DISCOVERY,
)
