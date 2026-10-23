"""
``JobQueue.run(job, work)``: run one registered job through the line, the memory guard and the ledger. systemd stays the clock; this is what each timer's
process does between "the timer fired" and "the job's command runs".

For a job that takes the shared lock:
1. it joins the line (``line.py``). A second invocation of a job already waiting - or of a collector/housekeeping/publication job already RUNNING - is
   COALESCED: logged and dropped, because the one in front will run once when the lock is free (a missed slot never piles up);
2. it may try the lock only when no waiter is ahead of it (class, then nearer deadline, then arrival) and the memory guard passes. A running lower-priority
   job is never killed, except a job registered ``preemptible`` (idempotent housekeeping) which an editorial/publication waiter SIGTERMs after
   ``PREEMPT_AFTER_MIN``, if ``PREEMPT_HOUSEKEEPING`` is on;
3. past its max wait (class default, capped at its own cadence) it is SKIPPED with the reason, in the ledger and, for editorial/publication jobs, in
   ``~/ops-log.md`` and the exit code. Nothing is dropped silently.
Lock-free jobs (watchdog, live feeds, ...) never wait; they are only ledgered. Every run ends with one ledger row: duration, exit, peak RSS, lock wait and who held it.
The paid-job guarantees (kill switch, runner claim, spend halt, one retry) live in ``work`` (ops/schedule.py) and are untouched.
"""

from __future__ import annotations

import signal
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from algent_backend.ops import opslog

from . import flags, guard, measure
from .env import Env
from .ledger import Ledger
from .line import Entry, Line


class Preempted(BaseException):
    """Raised inside a preemptible job's process when a higher-priority waiter SIGTERMs it."""


def max_wait_s(job: Any) -> float:
    if job.max_wait_min:
        return job.max_wait_min * 60
    cap = flags.MAX_WAIT_MIN[job.prio]
    return min(cap, job.every_min) * 60 if job.every_min else cap * 60


def deadline_epoch(job: Any, queued: float) -> float:
    """Epoch by which the job should finish (``deadline_min`` after its slot), 0 when it has none."""
    if not job.deadline_min:
        return 0.0
    q = datetime.fromtimestamp(queued, UTC)
    slot = q
    if job.hhmm():
        h, m = (int(x) for x in job.hhmm().split(":"))
        slot = q.replace(hour=h, minute=m, second=0, microsecond=0)
        if slot - q > timedelta(hours=12):
            slot -= timedelta(days=1)
    return (slot + timedelta(minutes=job.deadline_min)).timestamp()


class JobQueue:
    def __init__(self, env: Env | None = None, ledger: Ledger | None = None) -> None:
        self.env = env or Env()
        self.ledger = ledger or Ledger()
        self.line = Line(self.env)

    # ── the entry point ──
    def run(self, job: Any, work: Callable[[], int], *, parent: str = "") -> int:
        env, queued = self.env, self.env.now()
        row: dict[str, Any] = {"kind": "run", "job": job.name, "prio": job.prio, "locked": bool(job.lock), "parent": parent, "queued_at": queued}
        deadline = deadline_epoch(job, queued)
        history = self.ledger.rows() if job.lock else []
        handle = None
        if job.lock:
            handle, outcome = self._wait_for_lock(job, row, queued, deadline, history)
            if handle is None:
                return self._finish_unrun(job, row, outcome)
        start = env.now()
        row.update(start=start, wait_s=round(start - queued, 1), mem_avail_mb=_r(env.mem_available_mb()), svc=env.services_rss_mb())
        measure.reset()
        rc, outcome = 1, "failed"
        try:
            with _preempt_handler(job):
                rc = work()
            outcome = "ok" if rc == 0 else "failed"
        except Preempted:
            rc, outcome = 0, "preempted"
        except BaseException:
            outcome = "failed"
            self._write(job, row, outcome, rc=1)
            raise
        finally:
            if handle is not None:
                handle.close()
                self.line.clear_holder()
        if deadline and env.now() > deadline:
            row["deadline_missed"] = True
        self._write(job, row, outcome, rc=rc)
        return rc

    # ── waiting ──
    def _wait_for_lock(self, job: Any, row: dict[str, Any], queued: float, deadline: float, history: list[dict[str, Any]]) -> tuple[Any | None, str]:
        """(lock handle, "") once it is this job's turn, or (None, "skipped" | "coalesced") with ``row['reason']`` set."""
        env, line = self.env, self.line
        me = Entry(job.name, job.prio, deadline, queued, env.pid())
        holder = line.holder()
        if job.prio >= flags.PUBLICATION and holder and holder.get("job") == job.name and holder.get("pid") != env.pid():
            row["reason"] = f"already running (pid {holder['pid']}); its next run covers this slot"
            return None, "coalesced"
        twin = line.join(me)
        if twin is not None:
            row["reason"] = f"already waiting (pid {twin.pid}); it runs once when the lock is free"
            return None, "coalesced"
        limit, breached, preempted = max_wait_s(job), False, False
        try:
            while True:
                reason = ""
                ahead = line.ahead_of(me)
                if ahead:
                    reason = f"waiting behind {_names(ahead)}"
                elif flags.GUARD_ENABLED:
                    v = guard.check(job, history, env.mem_available_mb(), env.services_rss_mb())
                    if not v.ok:
                        reason = v.reason()
                        if not breached:
                            breached = True
                            self.ledger.append({"kind": "breach", "job": job.name, "avail_mb": _r(v.avail_mb), "need_mb": v.need_mb, "floor_mb": v.floor_mb}, now=_dt(env.now()))
                if not reason:
                    handle = env.try_lock()
                    if handle is not None:
                        line.leave(job.name)
                        line.set_holder(job.name, job.prio, job.preemptible, env.now())
                        return handle, ""
                    h = line.holder() or {}
                    reason = f"lock held by {h.get('job', 'another job')}"
                    row["waited_for"] = h.get("job", "?")
                    if not preempted and self._maybe_preempt(job, h, env.now() - queued):
                        preempted = True
                if env.now() - queued >= limit:
                    row["reason"] = f"busy: {reason} (waited {(env.now() - queued) / 60:.0f} min, max {limit / 60:.0f})"
                    row["wait_s"] = round(env.now() - queued, 1)
                    line.leave(job.name)
                    return None, "skipped"
                env.sleep(flags.POLL_S)
        except BaseException:
            line.leave(job.name)
            raise

    def _maybe_preempt(self, job: Any, holder: dict[str, Any], waited_s: float) -> bool:
        """SIGTERM a preemptible lower-priority holder once a higher-priority job (editorial/publication) has waited long enough."""
        if not (flags.PREEMPT_HOUSEKEEPING and holder.get("preemptible") and job.prio <= flags.PUBLICATION and job.prio < int(holder.get("prio") or 0)
                and waited_s >= flags.PREEMPT_AFTER_MIN * 60):
            return False
        self.env.terminate(int(holder["pid"]))
        return True

    # ── ledger rows ──
    def _finish_unrun(self, job: Any, row: dict[str, Any], outcome: str) -> int:
        row.setdefault("wait_s", round(self.env.now() - row["queued_at"], 1))
        self._write(job, row, outcome, rc=0)
        print(f"{job.name}: {outcome}: {row.get('reason', '')}", flush=True)
        if outcome == "skipped" and job.prio <= flags.PUBLICATION:
            opslog.append("jobq", f"{job.name}: SKIPPED, {row.get('reason', '')}", home=self.env.home, now=_dt(self.env.now()))
            return 1                                              # an editorial/publication job that did not run is a failure to systemd, a collector is policy
        return 0

    def _write(self, job: Any, row: dict[str, Any], outcome: str, *, rc: int) -> None:
        end = self.env.now()
        row.update(outcome=outcome, rc=rc, end=end)
        if "start" in row:
            row["duration_s"] = round(end - row["start"], 1)
            row["peak_rss_mb"] = measure.peak_mb()
        quiet = (not job.lock and outcome == "ok" and 0 < job.every_min < flags.LEDGER_QUIET_EVERY_MIN
                 and row.get("duration_s", 0) < flags.LEDGER_QUIET_BELOW_S)
        if not quiet:
            self.ledger.append(row, now=_dt(end))


class _preempt_handler:
    """While a preemptible job runs, SIGTERM raises ``Preempted`` in this process (the work's child is terminated by ``measure.call``)."""

    def __init__(self, job: Any) -> None:
        self.on, self.old = bool(job.preemptible and flags.PREEMPT_HOUSEKEEPING), None

    def __enter__(self) -> None:
        if self.on:
            try:
                self.old = signal.signal(signal.SIGTERM, self._raise)
            except (ValueError, OSError):                         # not the main thread
                self.on = False

    def __exit__(self, *exc: object) -> None:
        if self.on:
            signal.signal(signal.SIGTERM, self.old or signal.SIG_DFL)

    @staticmethod
    def _raise(_sig: int, _frame: Any) -> None:
        raise Preempted


def _names(entries: list[Entry]) -> str:
    return ", ".join(f"{flags.CLASS_NAMES[e.prio]} {e.job}" for e in entries[:3]) + (f" (+{len(entries) - 3})" if len(entries) > 3 else "")


def _r(x: float | None) -> float | None:
    return None if x is None else round(x)


def _dt(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)
