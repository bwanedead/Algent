"""
Prompt assembly — two distinct mechanisms, kept separate on purpose.

``compose_system_prompt`` builds the agent's *system prompt*: its nested,
arbitrary-depth identity (universal -> family -> specialization -> ...). This is
who the agent is, fixed for the agent regardless of the run.

``stitch_message`` builds a *task / user message* from conditional segments: the
runtime payload for one invocation, including the optional query seed a caller
provides. Segments that are absent (``None`` or blank) drop out, so a caller can
pass an optional segment unconditionally and let it disappear when irrelevant.

These are different things — identity vs. this run's task — and must not be
conflated. They share one trivial join; only their intent differs.
"""

from __future__ import annotations

_SEPARATOR = "\n\n"


def _join_nonempty(parts: tuple[str | None, ...]) -> str:
    return _SEPARATOR.join(p.strip() for p in parts if p and p.strip())


def compose_system_prompt(*layers: str) -> str:
    """Join system-prompt layers, broad to specific, into one identity prompt.

    For the agent's fixed identity only — never a caller's query seed or other
    per-run input. Any number of layers; blank layers are skipped.
    """
    return _join_nonempty(layers)


def stitch_message(*segments: str | None) -> str:
    """Stitch conditional task-message segments into one user message.

    Each segment is included only when present (non-``None``, non-blank), so an
    optional segment — e.g. a user-provided query seed — can be passed
    unconditionally and simply drop out when it does not apply. This is the
    per-run task payload, distinct from the fixed system prompt.
    """
    return _join_nonempty(segments)
