"""
Consumption API — how the rest of Ohmega reads the numbers layer.

* ``evidence_block(tags, as_of=...)`` — plain text for an agent's context: one line per matching
  series (latest value, unit, as-of, changes, unusual flag, source URL). Every figure is a
  programmatic reading with a citation; the text carries no interpretation, so the reader (a
  model or a person) decides what it means.
* ``moves_board(tags)`` — the same readings as dicts, for the site, maps, watches and Pulses.

Both read the store only (never the network) and accept ``as_of`` to replay "what did the numbers
say then". Series with nothing stored are omitted rather than shown empty.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from . import store
from .catalog import match
from .moves import series_moves


def moves_board(tags: list[str] | None = None, *, as_of: date | None = None) -> list[dict[str, Any]]:
    """Moves for every stored series matching ``tags`` (None = all); unusual ones first."""
    rows = [m for s in match(tags) if (m := series_moves(s, store.history(s.id), as_of=as_of, today=date.today()))]
    return sorted(rows, key=lambda m: (not m["unusual"], m["series_id"]))


def _num(x: float) -> str:
    if x == int(x) and abs(x) < 1e15:
        return f"{int(x):,}"
    return f"{x:,.4g}" if abs(x) < 10 else f"{x:,.2f}"


def _chg(c: dict[str, Any]) -> str:
    pct = f" ({c['pct']:+.0f}%)" if c["pct"] is not None else ""
    return f"{c['abs']:+,.4g}{pct}"


def _line(m: dict[str, Any]) -> str:
    ch = m["changes"]
    parts = [f"{label} {_chg(ch[key])}" for label, key in (("vs prev", "prev"), ("vs 7d", "7d"),
                                                          ("vs 30d", "30d"), ("vs 1y", "1y")) if key in ch]
    flags = []
    if m["unusual"]:
        zs = ", ".join(f"{r} z={m[r + '_z']}" for r in m["unusual_reasons"])
        flags.append(f"UNUSUAL vs own history ({zs})")
    if m["long_run_outside"]:
        flags.append(f"outside its full-history range (z={m['long_run_z']})")
    flags += [f"at {m[k]} {k[4:]}" for k in ("new_high", "new_low") if m[k]]
    tail = "; ".join([*parts, f"1y percentile {m['percentile_1y']:.0f}", *flags])
    internal = "" if m["public_display"] else " [internal source]"
    return (f"- {m['name']} [{m['series_id']}]: {_num(m['latest']['value'])} {m['unit']} as of "
            f"{m['latest']['period']} ({m['age_days']}d old); {tail}; source: {m['source']}{internal} {m['source_url']}")


def evidence_block(tags: list[str], *, as_of: date | None = None) -> str:
    """Text for agents: the matching series' latest readings and moves; '' when none are stored."""
    rows = moves_board(tags, as_of=as_of)
    if not rows:
        return ""
    head = (f"INSTRUMENTS — programmatic readings (no model), as of {(as_of or date.today()).isoformat()}; "
            "'unusual' means outside the series' own history, not a forecast:")
    return "\n".join([head, *map(_line, rows)])
