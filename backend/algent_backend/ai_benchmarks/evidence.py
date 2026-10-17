"""
Desk consumption — the benchmark tracker as cited evidence for AI theaters, the way ``instruments/evidence`` serves geopolitics.

Reads the store only (never the network). ``block`` renders a bounded text block for a writer's prompt: the headline index, the benchmarks
where a new measured record was set recently, and lab-claimed scores clearly marked as unverified. Measured sources are returned as citable URLs;
claims are not (a lab's own number must be attributed to the lab, never stated as established fact).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from . import derive, store

MAX_RECORD_LINES = 6
MAX_CLAIM_LINES = 4
CLAIM_DAYS = 21


def _pct(v: dict, score: float) -> str:
    return f"{score * 100:.1f}%" if v["unit"] == "fraction" else f"{score:,.0f}" if v["unit"] in ("elo", "points") else f"{score:g} {v['unit']}"


def block(*, as_of: date | None = None) -> tuple[str, set[str], int]:
    """(text, citable urls, lines) for the AI desk. ``("", set(), 0)`` when nothing is stored."""
    day = as_of or datetime.now(UTC).date()
    results = store.current()
    if not results:
        return "", set(), 0
    views = [v for b in store.benchmarks().values() if (v := derive.view(b, results, as_of=day))]
    lines, urls = [], set()
    recent = sorted((v for v in views if v["new_records"]), key=lambda v: v["new_records"][-1]["d"], reverse=True)[:MAX_RECORD_LINES]
    for v in recent:
        r = v["new_records"][-1]
        lag = v["open_lag_days"]
        tail = f"; open-weights best {_pct(v, v['open'][-1]['s'])} ({v['open'][-1]['m']})" + (f", about {round(lag / 30)} months behind" if lag and lag > 30 else "") if v["open"] else ""
        sat = f"; {v['saturation'] * 100:.0f}% of the ceiling" if v["saturation"] is not None else ""
        lines.append(f"- {v['name']}: new measured record {_pct(v, r['s'])} by {r['m']} ({r['d']}){tail}{sat} [{v['source_url']}]")
        urls.add(v["source_url"])
    since = (day - timedelta(days=CLAIM_DAYS)).isoformat()
    claims = [(v, c) for v in views for c in v["claimed"] if c["d"] >= since][:MAX_CLAIM_LINES]
    out = []
    if lines:
        out.append("OHMEGA AI BENCHMARKS (measured by independent leaderboards; as of " + day.isoformat() + "):\n" + "\n".join(lines))
    if claims:
        out.append("LAB-CLAIMED SCORES (the lab's own blog or model card; UNVERIFIED, attribute them to the lab and never state them as established):\n"
                   + "\n".join(f"- {c['lab_name'] or c['m']} says {c['m']} scores {_pct(v, c['s'])} on {v['name']} ({c['d']}) [{c['url']}]" for v, c in claims))
    return "\n\n".join(out), urls, len(lines) + len(claims)


def stale_note() -> str:
    """One line when any free source is stale, so the desk does not write 'no new records' off a feed that stopped (empty when all are fresh)."""
    from . import freshness

    bad = [h["name"] for h in freshness.source_health() if h["stale"]]
    return f"NOTE: benchmark sources not currently updating: {', '.join(bad)}." if bad else ""

