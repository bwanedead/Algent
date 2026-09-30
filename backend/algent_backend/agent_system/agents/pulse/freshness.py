"""
Freshness — how much reality has happened since Ohmega last reconciled a situation.

"Last updated yesterday" does not mean fresh; "three weeks ago" does not mean stale. What matters
is whether relevant things have happened since. So every daily headline radar is sorted into the
situations it touches, and each situation keeps an append-only record of those sightings.

A situation's UNPROCESSED count is the headlines sighted after its Pulses were last assessed from
researched evidence. The radar can make a Pulse stale; it can never move one — these are other
outlets' headlines, unverified, and only graded research is evidence (docs/architecture/pulse-system.md).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .catalog import SeedSituation
from .seed import attach


def record_radar(context: Any, config: Any, store: Any, portfolio: dict, *, attach_spec: Any,
                 edition: str) -> dict[str, int]:
    """Sort one radar edition into the situations it touches. Returns new sightings per situation."""
    situations = [s for s in store.situations() if s.status == "active"]
    vectors = [v for v in portfolio.get("vectors") or [] if isinstance(v, dict) and v.get("id")]
    if not situations or not vectors:
        return {}
    as_seed = tuple(SeedSituation(s.id, s.title, s.summary or s.title, s.domain) for s in situations)
    items = [{"id": v["id"], "title": v.get("title", ""), "summary": v.get("thesis", "")} for v in vectors]
    links = attach(context, config, items, situations=as_seed, model_spec=attach_spec)
    by_id = {v["id"]: v for v in vectors}
    now = datetime.now(UTC).isoformat()
    counts: dict[str, int] = {}
    for sit_id, ids in links.items():
        rows = [{"key": f"{edition}:{vid}", "at": now, "edition": edition,
                 "headline": by_id[vid].get("title", "")} for vid in ids]
        added = store.add_sightings(sit_id, rows) if rows else 0
        if added:
            counts[sit_id] = added
    return counts


def unprocessed(store: Any, situation_id: str) -> list[dict]:
    """Radar sightings since this situation's Pulses were last assessed from research."""
    last = max((i.at for p in store.pulses(situation_id) for i in store.log(p.id)
                if i.mode in ("seed", "article", "reassess")), default="")
    return [r for r in store.sightings(situation_id) if r["at"] > last]


def record_quietly(portfolio: dict, *, edition: str) -> dict:
    """The menu build's entry point. Never raises."""
    try:
        from algent_backend.agent_system.foundation.models import ModelResolver, house_spec
        from algent_backend.agent_system.runs.context import AgentRunContext

        from .repository import pulse_store

        ctx = AgentRunContext(run_id=f"radar-{edition}", model_resolver=ModelResolver())
        return record_radar(ctx, None, pulse_store(), portfolio, edition=edition,
                            attach_spec=house_spec(reasoning_effort="low", temperature=0.1))
    except Exception as exc:  # noqa: BLE001 — freshness is a signal, never a failure
        return {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
