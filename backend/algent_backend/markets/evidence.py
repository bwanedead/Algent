"""
The evidence a forecast is shown. BLIND BY CONSTRUCTION: this module never imports the price snapshots and ``build`` takes no price, so nothing
the market believes can reach the model. What the desk knows is the only input: the newest daily's sections for the theaters the market maps to
(with their Pulses and on-the-record statements), the calendar items for its countries, recent statements, live/anomaly/maritime blocks and
recent sanctions events. Each piece carries an id the forecast can cite (``theater:``, ``calendar:``, ``statement:``, ``sanction:``, ``desk:``).

Everything is read from local stores, best-effort: a missing store is simply a missing block, and "no evidence" is a legitimate input (the
forecaster is told to fall back to base rates and say so).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import flags
from .contracts import Market


@dataclass
class Evidence:
    text: str = ""
    ids: list[str] = field(default_factory=list)
    n_blocks: int = 0


def latest_record(domain: str = "geopolitics", root: Path | None = None) -> dict[str, Any]:
    from algent_backend.agent_system.agents.intel.daily import daily_dir

    folder = root or daily_dir(domain)
    for p in reversed(sorted(folder.glob("*.json")) if folder.is_dir() else []):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def _clip(text: Any, n: int) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _section_block(s: dict[str, Any], day: str) -> str:
    lines = [f"[theater:{s.get('theater_id')}] {s.get('name', '')} (daily of {day})"]
    for label, key in (("Bottom line", "bottom_line"), ("Since yesterday", "since_yesterday"), ("Outlook", "outlook")):
        if s.get(key):
            lines.append(f"  {label}: {_clip(s[key], 600)}")
    if s.get("watch_next"):
        wn = s["watch_next"] if isinstance(s["watch_next"], list) else [s["watch_next"]]
        lines.append("  Watch next: " + " | ".join(_clip(w, 160) for w in wn[:4]))
    for d in (s.get("developments") or [])[:4]:
        lines.append(f"  - {_clip(d.get('headline'), 140)} ({d.get('verification', 'reported')})")
    for p in s.get("pulses") or []:
        if p.get("position") is not None:
            lines.append(f"  Pulse {p.get('name')}: {p.get('position')}/100 ({p.get('band')}; 7-day change {p.get('change_7d')})")
    return "\n".join(lines)


def _calendar(countries: list[str], theaters: list[str], today: date) -> tuple[list[str], list[str]]:
    try:
        from algent_backend.lookahead import store as cal

        rows = [i for i in cal.upcoming(today, 90) if set(i.countries) & set(countries) or set(i.theaters) & set(theaters)][: flags.EVIDENCE_CALENDAR]
    except Exception:  # noqa: BLE001
        return [], []
    return ([f"[calendar:{i.id}] {i.date}: {i.title} ({i.kind}, {i.confidence} confidence)" for i in rows], [f"calendar:{i.id}" for i in rows])


def _statements(countries: list[str], today: date) -> tuple[list[str], list[str]]:
    try:
        from algent_backend.actors import registry
        from algent_backend.agent_system.agents.statements import store as st

        names = [registry.display_name(c) for c in countries if registry.display_name(c)]
        rows = st.query(terms=names, days=30, today=today, limit=flags.EVIDENCE_STATEMENTS) if names else []
    except Exception:  # noqa: BLE001
        return [], []
    return ([f"[statement:{s.id}] {s.date} {s.speaker} ({s.affiliation or s.role}): {_clip(s.paraphrase or s.quote, 220)}" for s in rows],
            [f"statement:{s.id}" for s in rows])


def _sanctions(countries: list[str], today: date) -> tuple[list[str], list[str]]:
    try:
        from algent_backend.actors import registry
        from algent_backend.sanctions import store as sx

        want = {c.casefold() for c in countries} | {registry.display_name(c).casefold() for c in countries}
        floor = (today - timedelta(days=30)).isoformat()
        rows = [e for e in sx.events() if not e.baseline and e.observed_on >= floor and want & {c.casefold() for c in e.countries}][-4:]
    except Exception:  # noqa: BLE001
        return [], []
    return ([f"[sanction:{e.id}] {e.date} {e.source} {e.action}: {e.name}" for e in rows], [f"sanction:{e.id}" for e in rows])


def _desk_blocks(countries: list[str]) -> list[str]:
    """The live / anomaly / maritime blocks the daily writers see, for the market's countries (they speak in country names)."""
    try:
        from algent_backend.actors import registry
        from algent_backend.live import desk as live_desk
        from algent_backend.live.memory import desk as memory_desk
        from algent_backend.maritime import desk as maritime_desk

        names = {registry.display_name(c) for c in countries if registry.display_name(c)}
        return [t for t in (live_desk.block(names)[0], memory_desk.block(names)[0], maritime_desk.block(names)[0]) if t]
    except Exception:  # noqa: BLE001
        return []


def build(market: Market, *, today: date, record: dict[str, Any] | None = None) -> Evidence:
    """The blind evidence for one market. ``record`` is the daily to read (default: the newest on disk)."""
    record = record if record is not None else latest_record()
    day = str(record.get("date") or "")
    by_id = {s.get("theater_id"): s for s in record.get("theaters") or [] if isinstance(s, dict)}
    parts, ids = [], []
    for tid in market.theaters[: flags.EVIDENCE_SECTIONS]:
        if tid in by_id:
            parts.append(_section_block(by_id[tid], day))
            ids.append(f"theater:{tid}")
    for lines, got in (_calendar(market.countries, market.theaters, today), _statements(market.countries, today),
                       _sanctions(market.countries, today)):
        if lines:
            parts.append("\n".join(lines))
            ids += got
    desk_blocks = _desk_blocks(market.countries)
    if desk_blocks:
        parts.append("\n\n".join(desk_blocks))
        ids.append("desk:live")
    return Evidence(text="\n\n".join(parts), ids=ids, n_blocks=len(parts))
