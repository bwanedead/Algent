"""
Operator-facing newsroom toggles (env-gated pauses, not soft-cap budget policy).

These are durable hand-switches for how the ladder runs today — e.g. pause synthesis
while a human picks raw t0 leads. Soft-cap optionality stays in ``budget_policy``.
"""

from __future__ import annotations

import os

_SYNTHESIS_ENV = "ALGENT_SYNTHESIS"


def synthesis_enabled() -> bool:
    """False when synthesis is paused (``ALGENT_SYNTHESIS=0/false/off``). Default on.

    Pause for manual t0 picking; re-enable for unattended / scheduled selection.
    """
    return os.environ.get(_SYNTHESIS_ENV, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
