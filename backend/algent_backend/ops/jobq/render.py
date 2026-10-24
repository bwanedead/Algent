"""Plain-text views of the ledger and the capacity report (``newsroom products runs`` / ``capacity``). Pure: data in, string out."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import flags
from .ledger import Ledger, stats


def _f(x: float | None, nd: int = 1) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def runs_data(ledger: Ledger | None = None, days: float = 7, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    rows = (ledger or Ledger()).rows(since=now - timedelta(days=days))
    return {"days": days, "jobs": stats(rows), "breaches": sum(r.get("kind") == "breach" for r in rows),
            "skips": [{"ts": r["ts"], "job": r["job"], "reason": r.get("reason", "")} for r in rows if r.get("outcome") == "skipped"]}


def runs_text(data: dict[str, Any]) -> str:
    head = f"{'job':18} {'runs':>4} {'fail':>4} {'skip':>4} {'coal':>4} | {'dur p50':>7} {'p95':>6} | {'wait p50':>8} {'p95':>6} {'max':>6} | {'rss p95':>7} | late"
    lines = [f"job runs, last {data['days']:g} days (minutes unless noted)", head, "-" * len(head)]
    for job, s in data["jobs"].items():
        lines.append(f"{job:18} {s['runs']:>4} {s['failed']:>4} {s['skipped']:>4} {s['coalesced']:>4} | {_f(s['p50_min']):>7} {_f(s['p95_min']):>6} | "
                     f"{_f(s['wait_p50_min']):>8} {_f(s['wait_p95_min']):>6} {_f(s['wait_max_min']):>6} | {_f(s['rss_p95_mb'], 0):>7} | {s['deadline_missed'] or ''}")
    if not data["jobs"]:
        lines.append("(no runs recorded yet: the ledger fills as the timers fire after the next deploy)")
    lines.append(f"memory-floor breaches: {data['breaches']}")
    for k in data["skips"][-10:]:
        lines.append(f"skipped {k['ts']} {k['job']}: {k['reason']}")
    return "\n".join(lines)


def capacity_text(r: dict[str, Any]) -> str:
    m, h, d = r["model"], r["measured"], r["new_desk"]
    out = [f"capacity at {r['at']}", "",
           f"MEASURED (run ledger, {h['runs_total']} rows): lock busy {h['busy_24h']:.0%} of 24 h, {h['busy_7d']:.0%} of 7 d; last 24 h: {h['24h']['runs']} runs, "
           f"{h['24h']['waited']} waited (p95 {h['24h']['wait_p95_min']:.0f} min), {len(h['24h']['skipped'])} skipped, {h['24h']['coalesced']} coalesced, "
           f"{h['24h']['breaches']} memory breaches, {len(h['24h']['deadline_missed'])} deadline misses",
           f"MODELLED day (calendars through the queue rule): lock busy {m['busy_min']} min = {m['busy_share']:.0%} of 24 h; peak memory {m['peak_memory_mb']} MB at "
           f"{m['peak_memory_at']} UTC (services at their peaks + everything that can overlap); tight hours (>= {flags.TIGHT_HOUR_SHARE:.0%} busy): "
           f"{', '.join(m['tight_hours']) or 'none'}",
           f"  durations from the ledger for {len(m['sources']['ledger'])} jobs, from registry estimates for {len(m['sources']['estimate'])}"
           + (f" ({', '.join(m['sources']['estimate'][:8])}{'...' if len(m['sources']['estimate']) > 8 else ''})" if m["sources"]["estimate"] else ""),
           "  busy minutes by UTC hour: " + " ".join(f"{x:d}" for x in m["busy_by_hour_min"])]
    if m["waits"]:
        out.append("  modelled waits: " + "; ".join(f"{w['job']} {w['wait_min']} min{'' if w['outcome'] == 'ok' else ' (' + w['outcome'] + ')'}" for w in m["waits"][:6]))
    out.append(f"MEMORY GUARD: floor {r['memory']['floor_mb']:.0f} MB with no service seen; service peaks "
               + ", ".join(f"{k} {v:.0f} MB" for k, v in r["memory"]["services_peak_mb"].items()))
    if d:
        out.append(f"ONE MORE DESK (like {d['like']}, {d['minutes']} min, {d['source']}): best slot {d['best_slot']} UTC; lock busy {d['busy_before']:.0%} -> {d['busy_after']:.0%} "
                   f"(+{d['added_busy_min']} min); added waiting {d['added_wait_min']} min; skips {d['skips_after']}; tight hours after: {', '.join(d['tight_hours_after']) or 'none'}")
    out.append("SPLIT RULE: " + ("; ".join(r["split"]) + " -> plan the second droplet (docs/guides/worker-server.md)" if r["split"] else "no clause holds: one box is still enough"))
    return "\n".join(out)
