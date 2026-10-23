"""
Everything derived from the registry, as pure functions: the backup's coverage, the envelope's budgets, the timer list, the paid jobs, the docs table
and the site contract. Consumers import these instead of keeping their own hand lists.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .model import Budget, Job, Product, Store
from .registry import PRODUCTS


def products() -> tuple[Product, ...]:
    return PRODUCTS


def by_id(pid: str) -> Product | None:
    return next((p for p in PRODUCTS if p.id == pid), None)


def stores() -> list[tuple[Product, Store]]:
    return [(p, s) for p in PRODUCTS for s in p.stores]


def store(name: str) -> Store | None:
    return next((s for _, s in stores() if s.name == name), None)


def jobs() -> list[tuple[Product, Job]]:
    return [(p, j) for p in PRODUCTS for j in p.job_list()]


def job(name: str) -> tuple[Product, Job] | None:
    return next(((p, j) for p, j in jobs() if j.name == name), None)


# ── backups ──────────────────────────────────────────────────────────────────────────────────────
def backup_sources() -> dict[str, Path]:
    """What the nightly mirror and the R2 snapshot cover: every store of an irreplaceable product that is marked backed up, by its mirror folder name."""
    return {s.name: s.path() for p, s in stores() if p.irreplaceable and s.backed_up}


def excluded_stores() -> dict[str, str]:
    """Stores deliberately not backed up, with the reason the registry gives."""
    return {s.name: s.why_not for _, s in stores() if not s.backed_up}


def registered_envs() -> set[str]:
    return {s.env for _, s in stores() if s.env}


# ── envelope ─────────────────────────────────────────────────────────────────────────────────────
def budget_for(name: str) -> Budget | None:
    s = store(name)
    return s.budget if s else None


def store_roots() -> dict[str, Path]:
    """Every budgeted store on this machine by name (the envelope measures these)."""
    return {s.name: s.path() for _, s in sorted(stores(), key=lambda t: t[1].name) if s.budget}


# ── timers and paid jobs ─────────────────────────────────────────────────────────────────────────
def timers() -> list[tuple[Product, Job]]:
    return [(p, j) for p, j in jobs() if j.kind == "timer"]


def timer_command(j: Job) -> str:
    """What the unit runs, relative to infra/server: the shell script itself, or the one-line router with the job's name."""
    return j.script or f"jobs.sh {j.name}"


def timer_lines() -> list[str]:
    """``name<TAB>command<TAB>OnCalendar`` per timer: what ``infra/server/install_schedules.sh`` turns into systemd units."""
    return [f"{j.name}\t{timer_command(j)}\t{j.when()}" for _, j in timers()]


def paid_jobs() -> list[tuple[Product, Job]]:
    return [(p, j) for p, j in jobs() if j.spend == "paid"]


# ── docs table ───────────────────────────────────────────────────────────────────────────────────
TABLE_START, TABLE_END = "<!-- products:table:start (generated: `newsroom products table`) -->", "<!-- products:table:end -->"


def _mb(x: float) -> str:
    return f"{x:,.0f}" if x >= 10 or x == int(x) else f"{x:.1f}"


def _cadence(j: Job) -> str:
    if j.kind == "service":
        return "always on"
    return f"{j.hhmm()} UTC" if j.hhmm() else f"`{j.when()}`"


def table_markdown() -> str:
    """The register of products as one markdown table (docs/architecture/foundation.md section 3 embeds it)."""
    head = ["| Product | Stores (steady → fail, MB) | Irreplaceable | Growth control | Jobs | Publishes | Pages |", "|---|---|---|---|---|---|---|"]
    rows = []
    for p in PRODUCTS:
        st = "<br>".join(f"`{s.name}` {_mb(s.budget.steady_mb)} → {_mb(s.budget.fail_mb)}" + ("" if s.backed_up else " (not backed up)") if s.budget else f"`{s.name}`"
                         for s in p.stores) or "-"
        irr = ("**yes**: " if p.irreplaceable else "no: ") + p.why
        ret = "<br>".join(f"{r.kind}: {r.policy}" for r in p.retention) or "-"
        js = "<br>".join(f"`{j.name}` {_cadence(j)}{' (paid)' if j.spend == 'paid' else ' (capped)' if j.spend == 'capped' else ''}" for j in p.job_list()) or (f"manual: {p.manual}" if p.manual else "-")
        rows.append(f"| **{p.title}** (`{p.id}`) | {st} | {irr} | {ret} | {js} | {', '.join(f'`{k}`' for k in p.publishes) or '-'} | {', '.join(f'`{r}`' for r in p.site_routes) or '-'} |")
    return "\n".join(head + rows)


def embed(doc: str, table: str | None = None) -> str:
    """``doc`` with the generated table between its markers replaced."""
    table = table if table is not None else table_markdown()
    return re.sub(re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END), lambda _m: f"{TABLE_START}\n{table}\n{TABLE_END}", doc, flags=re.S)


# ── site contract ────────────────────────────────────────────────────────────────────────────────
def site_contract() -> dict[str, Any]:
    """The part of the registry the site needs: which product owns each page route, what each publishes and how fresh it should be. Generated into
    ``sites/ohmega-monster/lib/products.json``; a test keeps the file equal to this."""
    prods = []
    for p in PRODUCTS:
        cadences = [j.every_min for j in p.job_list() if j.kind == "timer" and j.every_min]
        prods.append({"id": p.id, "title": p.title, "routes": list(p.site_routes), "publishes": list(p.publishes), "feeds_from": list(p.feeds_from),
                      "refresh_minutes": min(cadences) if cadences else None})
    return {"schema": "ohmega.products/1", "products": prods}


def route_pattern(route: str) -> re.Pattern[str]:
    """Next.js notation to a regex: ``[x]`` is one segment, ``[...x]`` is the rest."""
    out = re.sub(r"\\\[\\\.\\\.\\\.[^\]]*\\\]", ".+", re.escape(route))
    out = re.sub(r"\\\[[^\]]*\\\]", "[^/]+", out)
    return re.compile(f"^{out}$")


def owner_of_route(route: str) -> str | None:
    """The product that lists a route (a concrete path like ``/daily/ai/2026-10-23`` or a pattern); None when nobody does. An exact listing wins over
    a pattern, so ``/daily/headlines`` is the menu's although ``/daily/[desk]`` would also match it."""
    route = "/" + route.strip("/") if route.strip("/") else "/"
    for p in PRODUCTS:
        if route in p.site_routes:
            return p.id
    for p in PRODUCTS:
        if any(route_pattern(r).match(route) or route_pattern(route).match(r) for r in p.site_routes):
            return p.id
    return None
