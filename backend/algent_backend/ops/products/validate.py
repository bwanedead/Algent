"""
Static validation of the registry itself (no machine needed): the rules a product entry must satisfy to be a product. ``validate()`` returns problems
as plain strings; ``tests/test_products_registry.py`` asserts it is empty and ``newsroom products check`` reports it.
"""

from __future__ import annotations

from pathlib import Path

from . import views
from .model import RETENTION_KINDS, SPEND, Product

PKG = Path(__file__).resolve().parents[2]            # …/algent_backend
#: An append-only store must be able to keep growing at its measured rate for at least this long before it reaches its fail line.
MIN_RUNWAY_WEEKS = 52


def _ref_problem(ref: str) -> str:
    if not ref:
        return ""
    path, _, symbol = ref.partition("::")
    f = PKG / path
    if not f.is_file():
        return f"ref {ref!r}: no such file"
    if symbol and symbol not in f.read_text(encoding="utf-8", errors="replace"):
        return f"ref {ref!r}: {symbol!r} not found in the file"
    return ""


def runway_weeks(p: Product) -> float | None:
    """Weeks an append-only product's stores can grow at their budgeted rate before the fail line (the smallest across stores); None if it has none."""
    weeks = [(s.budget.fail_mb - s.budget.steady_mb) / s.budget.growth_mb_week for s in p.stores if s.budget and s.budget.growth_mb_week > 0]
    return min(weeks) if weeks else None


def _product_problems(p: Product, job_names: set[str]) -> list[str]:
    out: list[str] = []
    tag = f"{p.id}:"
    if not p.what or not p.why:
        out.append(f"{tag} needs a description (`what`) and a reason for its irreplaceable verdict (`why`)")
    backed = [s for s in p.stores if s.backed_up]
    if p.irreplaceable != bool(backed):
        out.append(f"{tag} irreplaceable={p.irreplaceable} but {len(backed)} of its stores are backed up (an irreplaceable product backs up a store; a disposable one backs up none)")
    for s in p.stores:
        if not s.backed_up and len(s.why_not) < 20:
            out.append(f"{tag} store {s.name} is not backed up and gives no reason (`why_not`)")
        if s.budget is None:
            out.append(f"{tag} store {s.name} has no size budget")
        elif not (0 <= s.budget.steady_mb <= s.budget.warn_mb < s.budget.fail_mb) or len(s.budget.why) < 15:
            out.append(f"{tag} store {s.name}: budget must satisfy steady <= warn < fail and say why")
    if (p.stores or p.publishes) and not p.retention:
        out.append(f"{tag} keeps data but has no retention policy (unbounded growth)")
    if not p.stores and not p.retention:
        out.append(f"{tag} needs a retention entry (kind 'derived' when it keeps nothing)")
    for r in p.retention:
        if r.kind not in RETENTION_KINDS:
            out.append(f"{tag} retention kind {r.kind!r} is not one of {RETENTION_KINDS}")
        if r.kind in ("prune", "rollup") and not r.ref:
            out.append(f"{tag} {r.kind} retention must reference the code that does it")
        if (bad := _ref_problem(r.ref)):
            out.append(f"{tag} {bad}")
        if r.by.startswith("job:") and r.by[4:] not in job_names:
            out.append(f"{tag} retention runs by {r.by} but no such job is registered (a {r.kind} nothing triggers is no policy)")
        elif r.by and not r.by.startswith("job:") and r.by not in ("on-write", "manual"):
            out.append(f"{tag} retention `by` must be job:<name>, on-write or manual, not {r.by!r}")
        if r.kind in ("prune", "rollup") and not r.by:
            out.append(f"{tag} {r.kind} retention must say who applies it (`by`)")
    if any(r.kind == "append-only" for r in p.retention):
        weeks = runway_weeks(p)
        if weeks is not None and weeks < MIN_RUNWAY_WEEKS:
            out.append(f"{tag} append-only growth reaches its fail line in {weeks:.0f} weeks (< {MIN_RUNWAY_WEEKS}): budget a rollup, or raise the line and say why")
    if not p.job_list() and not p.manual and (p.stores or p.publishes):
        out.append(f"{tag} writes data but has no job and no `manual` note: say how it gets refreshed")
    seen: set[str] = set()
    for j in p.job_list():
        if j.name in seen:
            out.append(f"{tag} duplicate job {j.name}")
        seen.add(j.name)
        if j.spend not in SPEND:
            out.append(f"{tag} job {j.name}: spend {j.spend!r}")
        if j.kind == "timer" and (not j.when() or not j.every_min or not (j.argv or j.script)):
            out.append(f"{tag} timer {j.name} needs a calendar, an every_min and a command")
        if j.spend == "paid" and not j.hhmm():
            out.append(f"{tag} paid job {j.name} must be a daily `at` time (ops/schedule.py runs it)")
    return out


def validate() -> list[str]:
    """Every rule at once; empty means the registry is a coherent set of products."""
    out: list[str] = []
    ids = [p.id for p in views.products()]
    names = [s.name for _, s in views.stores()]
    envs = [s.env for _, s in views.stores() if s.env]
    jobs = [j.name for _, j in views.jobs()]
    for what, items in (("product id", ids), ("store name", names), ("store env", envs), ("job name", jobs)):
        out += [f"duplicate {what} {i!r}" for i in sorted({i for i in items if items.count(i) > 1})]
    job_names = set(jobs)
    for p in views.products():
        out += _product_problems(p, job_names)
        out += [f"{p.id}: feeds_from {f!r} is not a product" for f in p.feeds_from if f not in ids]
        for pat in p.heartbeat:
            if pat.split("/", 1)[0] not in names:
                out.append(f"{p.id}: heartbeat {pat!r} names no registered store")
    routes = [r for p in views.products() for r in p.site_routes]
    out += [f"duplicate site route {r!r}" for r in sorted({r for r in routes if routes.count(r) > 1})]
    out += _cycles()
    out += _then_problems()
    return out


def _then_problems() -> list[str]:
    """After-hooks (``Job.then``) must name registered timer jobs and must not chain back on themselves."""
    timers = {j.name: j for _, j in views.jobs() if j.kind == "timer"}
    out = []
    for name, j in timers.items():
        out += [f"job {name}: then {t!r} is not a registered timer job" for t in j.then if t not in timers]
    for start in timers:
        seen, frontier = set(), list(timers[start].then)
        while frontier:
            n = frontier.pop()
            if n == start:
                out.append(f"job {start}: then-chain comes back to {start}")
                break
            if n in seen or n not in timers:
                continue
            seen.add(n)
            frontier += timers[n].then
    return out


def _cycles() -> list[str]:
    graph = {p.id: set(p.feeds_from) for p in views.products()}
    out, state = [], {}

    def visit(n: str, path: list[str]) -> None:
        if state.get(n) == 2 or n not in graph:
            return
        if state.get(n) == 1:
            out.append("feeds_from cycle: " + " -> ".join([*path[path.index(n):], n]))
            return
        state[n] = 1
        for m in sorted(graph[n]):
            visit(m, [*path, n])
        state[n] = 2

    for n in graph:
        visit(n, [])
    return out
