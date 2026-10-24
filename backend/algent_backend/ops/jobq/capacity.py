"""
Capacity: how much of the one box the schedule uses, where it is tight, and what one more desk would cost. Two sources, never mixed up in the output:

- MEASURED (the run ledger): lock busy share over 24 h / 7 days, waits, skips, memory-guard breaches, deadline misses;
- MODELLED (``simulate``): one steady-state day of the registry's calendars run through the same rule as the real queue (single lock, class then deadline then
  arrival, no preemption, max-wait skips, coalescing, after-hooks queued when their parent ends), with each job's duration/peak from the ledger p50/p95 when
  ``MIN_SAMPLES`` runs exist, else the registry's estimate (``source`` says which). It is how the tight windows and the "one more desk" projection exist
  before a week of ledger does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import flags, guard
from .ledger import Ledger, percentile, stats

DAY_MIN = 1440


# ── calendars ────────────────────────────────────────────────────────────────────────────────────
def _expand(field_: str, limit: int) -> list[int]:
    if "," in field_:                                   # a list: ``8,14,20``
        return sorted({v for part in field_.split(",") for v in _expand(part, limit)})
    if field_ == "*":
        return list(range(limit))
    if "/" in field_:
        a, b = field_.split("/", 1)
        return list(range(int(a or 0), limit, int(b)))
    return [int(field_)]


def daily_starts(when: str) -> list[int]:
    """Minutes-of-day (UTC) at which an OnCalendar string fires on an ordinary day. A monthly calendar fires on no ordinary day: []."""
    parts = when.strip().split()
    time_part = parts[-1]
    if len(parts) > 1:
        day = parts[0].split("-")[-1]
        if day != "*":
            return []
    t = time_part.split(":")
    return sorted({h * 60 + m for h in _expand(t[0], 24) for m in _expand(t[1], 60)})


# ── what a job costs ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Cost:
    minutes: float
    mb: float
    source: str                   # "ledger" or "estimate"


def cost_of(job: Any, st: dict[str, dict[str, Any]]) -> Cost:
    s = st.get(job.name) or {}
    if s.get("runs", 0) >= flags.MIN_SAMPLES and s.get("p50_min") is not None:
        mb = s["rss_p95_mb"] if s.get("rss_samples", 0) >= flags.MIN_SAMPLES and s.get("rss_p95_mb") else (job.est_mb or flags.EST_MB[job.prio])
        return Cost(float(s["p50_min"]), float(mb), "ledger")
    return Cost(job.est_min or flags.EST_MIN[job.prio], job.est_mb or flags.EST_MB[job.prio], "estimate")


# ── the model ────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Sim:
    runs: list[dict[str, Any]] = field(default_factory=list)       # one entry per queued run on the reported day
    busy_by_hour: list[float] = field(default_factory=lambda: [0.0] * 24)       # lock-held minutes in each hour
    peak_mem_mb: float = 0.0
    peak_mem_at: str = ""

    @property
    def busy_min(self) -> float:
        return sum(self.busy_by_hour)


def _arrivals(jobs: list[Any], days: int) -> list[tuple[float, Any, str]]:
    return [(d * DAY_MIN + m, j, "") for j in jobs for d in range(days) for m in daily_starts(j.when())]


def simulate(jobs: list[Any], costs: dict[str, Cost], *, extra: list[tuple[Any, int]] | None = None, memory: bool = True) -> Sim:
    """Two days through the queue; the second is reported (it carries the first night's spill). ``extra`` adds hypothetical (job, minute-of-day) arrivals."""
    by_name = {j.name: j for j in jobs}
    arrivals = _arrivals([j for j in jobs if j.lock], 2) + [(float(d * DAY_MIN + m), j, "") for j, m in (extra or []) for d in (0, 1)]
    for _a, j, _p in arrivals:
        costs.setdefault(j.name, cost_of(j, {}))
    arrivals.sort(key=lambda a: a[0])
    pending: list[dict[str, Any]] = []
    free, sim, i = 0.0, Sim(), 0
    running: list[tuple[float, float, float]] = []                    # (start, end, mb) of every lock-held run
    while i < len(arrivals) or pending:
        if not pending and arrivals[i][0] > free:
            free = arrivals[i][0]
        while i < len(arrivals) and arrivals[i][0] <= free:
            t, j, parent = arrivals[i]
            i += 1
            if any(p["job"].name == j.name for p in pending) or (j.prio >= flags.PUBLICATION and any(r["job"] == j.name and r["end"] > t for r in sim.runs)):
                sim.runs.append({"job": j.name, "arrive": t, "outcome": "coalesced", "end": t, "start": t, "wait": 0.0, "parent": parent})
                continue
            pending.append({"job": j, "arrive": t, "parent": parent})
        if not pending:
            continue
        pending.sort(key=lambda p: (p["job"].prio, _deadline(p["job"], p["arrive"]), p["arrive"]))
        p = pending.pop(0)
        j, wait = p["job"], free - p["arrive"]
        if wait > _max_wait_min(j):
            sim.runs.append({"job": j.name, "arrive": p["arrive"], "outcome": "skipped", "end": free, "start": free, "wait": wait, "parent": p["parent"]})
            continue
        c = costs[j.name]
        start, end = free, free + c.minutes
        sim.runs.append({"job": j.name, "arrive": p["arrive"], "start": start, "end": end, "wait": wait, "outcome": "ok", "mb": c.mb, "parent": p["parent"]})
        running.append((start, end, c.mb))
        free = end
        for hook in j.then:
            h = by_name.get(hook)
            if h is not None and h.lock:
                costs.setdefault(h.name, cost_of(h, {}))
                arrivals.append((end, h, j.name))
                arrivals[i:] = sorted(arrivals[i:], key=lambda a: a[0])
    lo, hi = DAY_MIN, 2 * DAY_MIN
    for s, e, _mb in running:
        for m in range(int(max(s, lo)), int(min(e, hi))):
            sim.busy_by_hour[(m - lo) // 60] += 1.0
    sim.runs = [r for r in sim.runs if lo <= r["arrive"] < hi]
    if memory:
        _peak_memory(sim, jobs, costs, running)
    return sim


def _deadline(job: Any, arrive: float) -> float:
    return arrive + job.deadline_min if job.deadline_min else float("inf")


def _max_wait_min(job: Any) -> float:
    cap = job.max_wait_min or flags.MAX_WAIT_MIN[job.prio]
    return cap if job.max_wait_min or not job.every_min else min(cap, job.every_min)


def _peak_memory(sim: Sim, jobs: list[Any], costs: dict[str, Cost], running: list[tuple[float, float, float]]) -> None:
    """Resident services at their documented peaks + the lock holder + every lock-free job that is mid-run, over the reported day (an event sweep)."""
    events: list[tuple[float, float]] = []
    for s, e, mb in running:
        events += [(s, mb), (e, -mb)]
    for j in (j for j in jobs if not j.lock):
        c = costs.setdefault(j.name, cost_of(j, {}))
        for m in daily_starts(j.when()):
            events += [(DAY_MIN + m, c.mb), (DAY_MIN + m + max(c.minutes, 1.0), -c.mb)]
    used, best, at = 0.0, 0.0, DAY_MIN
    for t, d in sorted(events, key=lambda x: (x[0], x[1])):         # ends before starts at the same minute
        used += d
        if DAY_MIN <= t < 2 * DAY_MIN and used > best:
            best, at = used, int(t)
    sim.peak_mem_mb = round(sum(flags.SERVICE_PEAK_MB.values()) + best)
    sim.peak_mem_at = f"{(at - DAY_MIN) // 60:02d}:{(at - DAY_MIN) % 60:02d}"


# ── measured ─────────────────────────────────────────────────────────────────────────────────────
def busy_share(rows: list[dict[str, Any]], now: datetime, hours: float) -> float:
    """Share of the last ``hours`` the lock was held, from the ledger's locked runs (their start..end)."""
    lo, hi = (now - timedelta(hours=hours)).timestamp(), now.timestamp()
    spans = sorted((max(r["start"], lo), min(r["end"], hi)) for r in rows
                   if r.get("kind", "run") == "run" and r.get("locked") and r.get("start") and r.get("end") and r["end"] > lo and r["start"] < hi)
    total, cur_end = 0.0, lo
    for s, e in spans:                                                # a union: overlapping rows are not double-counted
        s = max(s, cur_end)
        if e > s:
            total += e - s
            cur_end = e
    return total / (hi - lo)


def queue_health(rows: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """What the envelope and the doctor show: waits, skips, breaches, deadline misses over 24 h and 7 d, and busy shares."""
    def since(h: float) -> list[dict[str, Any]]:
        lo = (now - timedelta(hours=h)).timestamp()
        return [r for r in rows if (_ep(r) or 0) >= lo]

    out: dict[str, Any] = {"busy_24h": busy_share(rows, now, 24), "busy_7d": busy_share(rows, now, 24 * 7), "runs_total": len(rows)}
    for label, h in (("24h", 24), ("7d", 24 * 7)):
        rs = since(h)
        runs = [r for r in rs if r.get("kind", "run") == "run"]
        waits = [r.get("wait_s", 0.0) / 60 for r in runs if r.get("outcome") in ("ok", "failed", "preempted")]
        out[label] = {
            "runs": len(runs), "waited": sum(w >= 1 for w in waits), "wait_p95_min": percentile(waits, 95) or 0.0,
            "skipped": [{"job": r["job"], "prio": r.get("prio", 3), "reason": r.get("reason", "")} for r in runs if r.get("outcome") == "skipped"],
            "coalesced": sum(r.get("outcome") == "coalesced" for r in runs),
            "breaches": sum(r.get("kind") == "breach" for r in rs),
            "deadline_missed": [r["job"] for r in runs if r.get("deadline_missed")],
        }
    return out


def _ep(r: dict[str, Any]) -> float | None:
    try:
        return datetime.fromisoformat(r["ts"]).timestamp()
    except (KeyError, ValueError):
        return None


# ── the split rule ───────────────────────────────────────────────────────────────────────────────
def split_triggers(health: dict[str, Any], projected_busy: float | None = None) -> list[str]:
    """Which clauses of the written split rule (docs/guides/worker-server.md) hold right now; empty means one box is still enough."""
    out = []
    if health["busy_7d"] >= flags.SPLIT_BUSY_7D:
        out.append(f"lock busy {health['busy_7d']:.0%} of the last 7 days (>= {flags.SPLIT_BUSY_7D:.0%})")
    w = health["7d"]
    if w["breaches"] >= flags.SPLIT_MEM_BREACHES_WEEK:
        out.append(f"{w['breaches']} memory-floor breaches in 7 days (>= {flags.SPLIT_MEM_BREACHES_WEEK})")
    if len(w["deadline_missed"]) >= flags.SPLIT_DEADLINE_MISSES_WEEK:
        out.append(f"{len(w['deadline_missed'])} deadline misses in 7 days (>= {flags.SPLIT_DEADLINE_MISSES_WEEK})")
    if any(s["prio"] <= flags.PUBLICATION for s in w["skipped"]):
        out.append("an editorial/publication job was skipped as busy in 7 days")
    if projected_busy is not None and projected_busy >= flags.SPLIT_BUSY_7D:
        out.append(f"the planned desk would put the lock at {projected_busy:.0%} (>= {flags.SPLIT_BUSY_7D:.0%})")
    return out


# ── the report ───────────────────────────────────────────────────────────────────────────────────
def report(ledger: Ledger | None = None, *, now: datetime | None = None, jobs: list[Any] | None = None, new_desk: str = "ai-daily") -> dict[str, Any]:
    """The capacity report as data (the CLI prints it): modelled day, measured health, the one-more-desk projection and the split verdict."""
    from algent_backend.ops.products import views

    now = now or datetime.now(UTC)
    rows = (ledger or Ledger()).rows(since=now - timedelta(days=flags.LEDGER_KEEP_DAYS))
    runs = [r for r in rows if r.get("kind", "run") == "run"]
    st = stats(runs)
    jobs = jobs if jobs is not None else [j for _p, j in views.timers()]
    costs = {j.name: cost_of(j, st) for j in jobs}
    sim = simulate(jobs, dict(costs))
    health = queue_health(rows, now)
    tight = [f"{h:02d}:00" for h in range(24) if sim.busy_by_hour[h] / 60 >= flags.TIGHT_HOUR_SHARE]
    waits = sorted(({"job": r["job"], "wait_min": round(r["wait"]), "outcome": r["outcome"]} for r in sim.runs if r["wait"] >= 1 or r["outcome"] != "ok"),
                   key=lambda r: -r["wait_min"])
    proj = project_new_desk(jobs, costs, sim, new_desk)
    return {
        "at": now.isoformat(timespec="seconds"),
        "model": {"busy_min": round(sim.busy_min), "busy_share": sim.busy_min / DAY_MIN, "busy_by_hour_min": [round(x) for x in sim.busy_by_hour], "tight_hours": tight,
                  "waits": waits[:12], "peak_memory_mb": sim.peak_mem_mb, "peak_memory_at": sim.peak_mem_at,
                  "sources": {"ledger": sorted(n for n, c in costs.items() if c.source == "ledger"),
                              "estimate": sorted(n for n, c in costs.items() if c.source == "estimate" and next(j for j in jobs if j.name == n).lock)}},
        "measured": health,
        "memory": {"floor_mb": guard.floor_mb(runs, {}), "services_peak_mb": guard.service_peaks(runs)},
        "new_desk": proj,
        "split": split_triggers(health, proj.get("busy_after") if proj else None),
    }


def project_new_desk(jobs: list[Any], costs: dict[str, Cost], base: Sim, like: str) -> dict[str, Any] | None:
    """Add one more daily of ``like``'s size (its duration, memory and after-hooks) at the least contended half-hour of the day and report what it costs."""
    ref = next((j for j in jobs if j.name == like), None)
    if ref is None:
        return None
    desk = _clone(ref, "new-desk")
    costs = dict(costs)
    costs["new-desk"] = costs[like]
    best: tuple[float, int, Sim] | None = None
    for slot in range(0, DAY_MIN, 30):
        s = simulate(jobs, dict(costs), extra=[(desk, slot)], memory=False)
        cost = sum(r["wait"] for r in s.runs) + 1000 * sum(r["outcome"] == "skipped" for r in s.runs)
        if best is None or cost < best[0]:
            best = (cost, slot, s)
    assert best is not None
    _c, slot, after = best
    before_wait = sum(r["wait"] for r in base.runs)
    return {"like": like, "minutes": round(costs[like].minutes), "source": costs[like].source, "best_slot": f"{slot // 60:02d}:{slot % 60:02d}",
            "busy_before": base.busy_min / DAY_MIN, "busy_after": after.busy_min / DAY_MIN, "added_busy_min": round(after.busy_min - base.busy_min),
            "added_wait_min": round(sum(r["wait"] for r in after.runs) - before_wait),
            "skips_after": sum(r["outcome"] == "skipped" for r in after.runs),
            "tight_hours_after": [f"{h:02d}:00" for h in range(24) if after.busy_by_hour[h] / 60 >= flags.TIGHT_HOUR_SHARE]}


def _clone(job: Any, name: str) -> Any:
    from dataclasses import replace

    return replace(job, name=name, calendar="", at="")
