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

from datetime import date, datetime
from typing import Any

from . import store
from .catalog import match
from .moves import series_moves


def _is_new(series: Any, row: dict[str, Any], ref: date) -> bool:
    """Did this reading arrive within the last day? A daily source always has something new; a weekly or monthly
    one is new only on the day its release lands, otherwise the same reading would be re-announced every day as
    a fresh move. Judged from when we first stored the latest period (``fetched_at``)."""
    if series.cadence == "daily":
        return True
    first = next((o for o in store.log(series.id) if o.period == row["latest"]["period"]), None)
    try:
        return first is None or (ref - datetime.fromisoformat(first.fetched_at).date()).days <= 1
    except ValueError:
        return True          # an unreadable stamp must not hide a reading


def moves_board(tags: list[str] | None = None, *, as_of: date | None = None) -> list[dict[str, Any]]:
    """Moves for every stored series matching ``tags`` (None = all). Rows carry ``new`` (see ``_is_new``); the
    ones that are unusual AND new come first."""
    ref = as_of or date.today()
    rows = []
    for s in match(tags):
        if m := series_moves(s, store.history(s.id), as_of=as_of, today=date.today()):
            rows.append({**m, "new": _is_new(s, m, ref)})
    return sorted(rows, key=lambda m: (not (m["unusual"] and m["new"]), m["series_id"]))


def _num(x: float) -> str:
    if x == int(x) and abs(x) < 1e15:
        return f"{int(x):,}"
    return f"{x:,.4g}" if abs(x) < 10 else f"{x:,.2f}"


def _chg(c: dict[str, Any], *, was: bool = False) -> str:
    pct = f" ({c['pct']:+.0f}%)" if c["pct"] is not None else ""
    # ``was`` names the earlier value the change is measured from: the only baseline a writer may quote.
    return f"{c['abs']:+,.4g}{pct}" + (f" [was {_num(c['from_value'])} on {c['from_period']}]" if was else "")


def _line(m: dict[str, Any]) -> str:
    ch, step = m["changes"], m["step_key"]
    labels = {"prev": f"vs {m['step_label']}" if step == "prev" else "vs prev", "7d": f"vs {m['step_label']}" if step == "7d" else "vs 7d",
              "30d": "vs 30d", "1y": "vs 1y"}
    parts = [f"{labels[k]} {_chg(ch[k], was=k != 'prev')}" for k in ("prev", "7d", "30d", "1y")
             if k in ch and not (k == "prev" and step != "prev")]
    flags = []
    if m["unusual"]:
        zs = ", ".join(f"{r} z={m[r + '_z']}" for r in m["unusual_reasons"])
        flags.append(f"UNUSUAL vs own history ({zs})" if m["new"]
                     else f"standing departure from own history ({zs}); NOT a new reading today, do not report as a move")
    if m["long_run_outside"]:
        flags.append(m["outside_note"] or "far from its usual level")
    flags += [f"at {m[k]} {k[4:]}" for k in ("new_high", "new_low") if m[k]]
    pw = m.get("percentile_window") or {}
    rank = (f"1y percentile {m['percentile_1y']:.0f}" if m.get("percentile_1y") is not None
            else f"percentile {pw['value']:.0f} within only {pw['days']}d of our history (not a year)" if pw else "")
    tail = "; ".join([*parts, *([rank] if rank else []), *flags])
    internal = "" if m["public_display"] else " [internal source]"
    fr = m["freshness"]
    when = f"{m['latest']['period']} ({fr['note']})" if fr["cadence"] != "daily" or fr["status"] == "overdue"         else f"{m['latest']['period']} ({m['age_days']}d old)"
    return (f"- {m['name']} [{m['series_id']}]: {_num(m['latest']['value'])} {m['unit']} as of "
            f"{when}; {tail}; source: {m['source']}{internal} {m['source_url']}")


def render_block(rows: list[dict[str, Any]], *, as_of: date | None = None) -> str:
    """The evidence text for already-chosen ``moves_board`` rows ('' for none): lets a consumer that
    ranks or budgets the rows itself print them in the one canonical format."""
    if not rows:
        return ""
    head = (f"INSTRUMENTS — programmatic readings (no model), as of {(as_of or date.today()).isoformat()}; "
            "'unusual' means outside the series' own history, not a forecast:")
    return "\n".join([head, *map(_line, rows)])


def evidence_block(tags: list[str], *, as_of: date | None = None) -> str:
    """Text for agents: the matching series' latest readings and moves; '' when none are stored."""
    return render_block(moves_board(tags, as_of=as_of), as_of=as_of)
