"""
Newsroom operator defaults — durable hand-switches agents edit in-repo.

These are standing mode toggles for how the ladder runs (e.g. synthesis on/off,
target portfolio size). They live in this file so operators are not asked to
manage ``.env`` for them.

Optional one-shot override: set ``ALGENT_<FLAG>`` in the process env for a single
run; when unset, the constant below wins. Soft-cap optionality stays in
``budget_policy``. Secrets stay in ``.env`` / keyring — never put keys here.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Standing defaults (edit these — do not ask the human to set .env for them)
# ---------------------------------------------------------------------------

# False = stop at the raw t0 pool menu (manual compose / pick). True = run t1
# synthesis into a research-vector menu (unattended / scheduled selection).
SYNTHESIS_ENABLED = True

# Soft target for how many research vectors synthesis should aim to return.
# Not a hard quota — thin pools may yield fewer; rich pools may go a bit over.
# Wired into the synthesis task message so the model sees the standing aim.
SYNTHESIS_TARGET_VECTORS = 40

BRIEFING_ENABLED = True
BRIEFING_MIN_ITEMS = 2
BRIEFING_MAX_ITEMS = 5
#: Minutes between briefing posts. Wider than Radar so a roundup does not sit on
#: every short-notice slot.
BRIEFING_SPACING_MIN = 90
#: How many themed roundups to queue from one menu. The rest wait for a later
#: portfolio — a full 40-vector menu would otherwise occupy the timeline all day.
BRIEFING_MAX_CLUSTERS = 6

# Structured final portfolio needs room: ~400 output tokens/vector is a safe
# planning figure (title+thesis+rationale+questions+sources). Default ReAct
# ceiling (4k) silently truncates larger portfolios into empty ``vectors``.
_SYNTHESIS_TOKENS_PER_VECTOR = 400
_SYNTHESIS_OUTPUT_FLOOR = 8_192
_SYNTHESIS_OUTPUT_CEILING = 32_768

# ---------------------------------------------------------------------------

_SYNTHESIS_ENV = "ALGENT_SYNTHESIS"
_BRIEFING_ENV = "ALGENT_BRIEFING"
_FALSEY = ("0", "false", "no", "off")


def synthesis_enabled() -> bool:
    """Whether the t1 synthesis stage runs.

    Standing default: ``SYNTHESIS_ENABLED`` in this file. Optional one-shot:
    ``ALGENT_SYNTHESIS=0/1`` when set.
    """
    raw = os.environ.get(_SYNTHESIS_ENV)
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in _FALSEY
    return bool(SYNTHESIS_ENABLED)


def synthesis_target_vectors() -> int:
    """Standing soft target for t1 portfolio size (see ``SYNTHESIS_TARGET_VECTORS``)."""
    return max(1, int(SYNTHESIS_TARGET_VECTORS))


def synthesis_max_output_tokens() -> int:
    """Output-token ceiling for the synthesis ReAct + structured portfolio call."""
    need = synthesis_target_vectors() * _SYNTHESIS_TOKENS_PER_VECTOR
    return max(_SYNTHESIS_OUTPUT_FLOOR, min(_SYNTHESIS_OUTPUT_CEILING, need))


def briefing_enabled() -> bool:
    raw = os.environ.get(_BRIEFING_ENV)
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in _FALSEY
    return bool(BRIEFING_ENABLED)


def briefing_min_items() -> int:
    return max(1, int(BRIEFING_MIN_ITEMS))


def briefing_max_items() -> int:
    return max(briefing_min_items(), int(BRIEFING_MAX_ITEMS))


def briefing_spacing_min() -> int:
    return max(15, int(BRIEFING_SPACING_MIN))


def briefing_max_clusters() -> int:
    return max(1, int(BRIEFING_MAX_CLUSTERS))
