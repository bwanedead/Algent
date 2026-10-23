"""
The product registry's vocabulary: plain frozen dataclasses, no behaviour that touches the world.

A *product* is anything we make or keep that has a store, a job, a publication or a page. Its entry says, in one place, everything the rest of
the system used to be told by hand: where its data lives, whether losing it is permanent, how its growth is bounded, how big it may get, which
jobs run it and when, what it publishes and which pages read it. Backups, the envelope, the systemd timers, the paid-job list, the docs table
and the site contract are all derived from these entries (``views.py``); ``check.py`` judges the live machine against them.

Store locations are zero-argument resolvers that import lazily, so reading the registry never imports a lab.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]            # …/Algent/backend
REPO = BACKEND.parent

#: How a store's growth is bounded. ``append-only`` (a corpus: bounded by a budget and a measured weekly growth, never by deletion),
#: ``overwrite`` (files are replaced, size is flat), ``prune`` / ``rollup`` (something deletes or folds old data on a schedule),
#: ``derived`` (rebuildable from other products; losing or clearing it costs compute only).
RETENTION_KINDS = ("append-only", "overwrite", "prune", "rollup", "derived")
#: A job's spend class: ``free``; ``capped`` (spends a little, behind its own cap); ``paid`` (goes through ``ops/schedule.py``: kill switch,
#: runner claim and spend halt).
SPEND = ("free", "capped", "paid")


def env_dir(env: str, default: str) -> Callable[[], Path]:
    """A resolver for a store whose root is ``$env`` or ``default`` (a relative path is relative to ``backend/``, as the backup has always read it)."""
    return lambda: Path(os.environ.get(env) or default)


@dataclass(frozen=True)
class Budget:
    """How big a store may be. Numbers in MB; ``why`` says where they come from."""

    steady_mb: float          # size today (measured 2026-10-23, or an estimate that ``why`` says is one)
    warn_mb: float            # size at which the envelope warns
    fail_mb: float            # size at which it fails
    written_mb: float         # MB modified inside a 7-day window that makes the envelope warn (growth for an append-only store, churn for a rewritten one)
    growth_mb_week: float     # expected net growth per week; the append-only runway test divides the headroom by this
    why: str


@dataclass(frozen=True)
class Store:
    """One directory a product writes. ``name`` is also the folder name in the backup mirror and the ``store:<name>`` envelope row."""

    name: str
    root: Callable[[], Path]
    env: str = ""                         # the ALGENT_* variable that moves it (a test asserts every such variable in the code is registered)
    backed_up: bool = False               # in the nightly git mirror and the R2 snapshot
    why_not: str = ""                     # required when not backed up: why losing it is acceptable
    budget: Budget | None = None

    def path(self) -> Path:
        p = self.root()
        return p if p.is_absolute() else BACKEND / p


@dataclass(frozen=True)
class Retention:
    """The policy that stops a product's storage growing without bound. ``ref`` is ``<path under algent_backend/>::<symbol>`` (the code or flag that
    implements it; a test checks it exists). ``by`` says who applies it: ``job:<name>`` (a registered job), ``on-write`` (the writer bounds itself)
    or ``manual`` (a command a person runs)."""

    kind: str
    policy: str
    ref: str = ""
    by: str = ""


@dataclass(frozen=True)
class Job:
    """One unit of scheduled work. ``argv`` is what follows ``python -m algent_backend.cli newsroom``; ``script`` (relative to infra/server) replaces it
    for the one job that is a shell script. ``calendar`` is a systemd OnCalendar string (UTC) or a zero-argument callable returning one (read from
    the product's own flags, so a time has one home). ``every_min`` is the longest gap between runs that is still healthy.
    ``then`` names jobs that follow a successful run: the daily that finishes a report triggers the fast views build and the site smoke test, so the pages
    reflect it within minutes instead of at the next timer tick."""

    name: str
    argv: tuple[str, ...] = ()
    calendar: str | Callable[[], str] = ""
    at: str | Callable[[], str] = ""      # alternatively "HH:MM" UTC daily (or a callable returning it): the form every scheduled paid job is written in
    every_min: float = 0.0
    spend: str = "free"
    lock: bool = True                     # takes the shared job lock (one heavy job at a time on this 4 GB machine); False for jobs that must not wait
    kind: str = "timer"                   # "timer", or "service" (always on, installed by hand; listed so it is not an orphan)
    what: str = ""
    script: str = ""
    then: tuple[str, ...] = ()            # after-hook: jobs run once this one has succeeded (``products/run.py``), each as its own run: its own lock and spend gates

    def hhmm(self) -> str:
        return (self.at() if callable(self.at) else self.at) or ""

    def when(self) -> str:
        """The OnCalendar string the timer is installed with."""
        if self.hhmm():
            return f"*-*-* {self.hhmm()}:00"
        return self.calendar() if callable(self.calendar) else self.calendar


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    owner: str                                            # the module that owns it (path under algent_backend/)
    what: str
    stores: tuple[Store, ...] = ()
    retention: tuple[Retention, ...] = ()
    irreplaceable: bool = False                           # losing it is permanent; True means at least one store is backed up
    why: str = ""                                         # the reason for the irreplaceable verdict, either way
    jobs: tuple[Job, ...] | Callable[[], tuple[Job, ...]] = ()
    manual: str = ""                                      # no timer on purpose: the command a person runs, and why
    publishes: tuple[str, ...] = ()                       # key prefixes in the publication bucket (R2)
    site_routes: tuple[str, ...] = ()                     # app routes that read it, in Next.js notation (/daily/[desk]/[date])
    feeds_from: tuple[str, ...] = ()                      # product ids it reads (for later dependency ordering)
    heartbeat: tuple[str, ...] = ()                       # "<store name>/<glob>": files whose newest mtime shows the product ran (the freshness check)
    notes: dict[str, str] = field(default_factory=dict)

    def job_list(self) -> tuple[Job, ...]:
        return tuple(self.jobs() if callable(self.jobs) else self.jobs)
