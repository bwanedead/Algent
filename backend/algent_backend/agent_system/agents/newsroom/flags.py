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

# ---------------------------------------------------------------------------

_SYNTHESIS_ENV = "ALGENT_SYNTHESIS"
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
