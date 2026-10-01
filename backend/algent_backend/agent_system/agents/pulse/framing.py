"""
How a Pulse is described to the model — its frame, and (unless blind) its history as the scale.

One home for this, used by the article update and the reassessment, so the two can never describe
the same Pulse differently. A Pulse's past readings are its memory and each new reading is argued
against them; alongside them the reader sees the recent ABSOLUTE votes of other readers, so the
collective's view of where reality sits reaches every reading (doctrine v4). The blind check gets
the frame only.
"""

from __future__ import annotations

from typing import Any

from .projection import VOTES, absolute_votes, project

#: Enough history to compare against; beyond this the oldest readings add little and cost tokens.
_HISTORY = VOTES


def describe(pulse: Any, log: list | None = None, *, blind: bool = False) -> str:
    d = pulse.definition
    lines = [f"PULSE {pulse.id} — {pulse.name}", d.question,
             f"  0 (calm): {d.low_end or _legacy_end(d, 0)}",
             f"  100 (extreme): {d.high_end or _legacy_end(d, 100)}"]
    if blind or log is None:
        return "\n".join(lines)
    readings = [i for i in log if i.mode != "blind" and (i.decision == "applied" or i.mode == "seed")]
    if not readings:
        lines.append("  PAST READINGS: none — this is its first placement.")
        return "\n".join(lines)
    lines.append("  PAST READINGS (oldest first) — the scale this Pulse is measured on:")
    for i in readings[-_HISTORY:]:
        where = "unassessed" if i.proposed_position is None else f"{i.proposed_position:g}"
        lines.append(f"    {i.at[:10]}: {where} — {' '.join(i.rationale.split())[:300]}")
    votes = absolute_votes(log)
    if votes:
        state = project(pulse.id, log)
        held = "unassessed" if state.position is None else f"{state.position:g}"
        lines.append(f"  ABSOLUTE VOTES — where {len(votes)} independent reader(s) put reality, ignoring the "
                     f"history (median {state.absolute_view:g}; the Pulse holds {held}):")
        for v in votes:
            lines.append(f"    {v.at[:10]}: {v.absolute_position:g} — {' '.join(v.rationale.split())[:160]}")
    return "\n".join(lines)


def _legacy_end(definition: Any, position: float) -> str:
    """Pulses seeded under the fixed-ruler doctrine carry anchors instead of ends."""
    hit = next((a for a in definition.anchors if a.position == position), None)
    return hit.meaning if hit else "—"
