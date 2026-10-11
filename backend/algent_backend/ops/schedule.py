"""
``newsroom schedule run <job>`` — the unattended PAID jobs: the geopolitics daily's two editions and the menu.

The operator authorised these to run on a timer, protected by the watchdog (``ops/watchdog.py``). This wrapper is
what each paid systemd unit starts (via ``infra/server/jobs.sh``, which holds the shared job lock first, so paid
jobs never overlap each other or the free ones). It spends nothing itself; it only decides WHETHER the real
command runs, then runs it as a child process (so the watchdog sees and limits the child on its own command line)
and writes down what happened.

Before spending it checks, in order, and exits 0 ("skipped", not a failure) on any no:
1. the kill switch (``flags.SCHEDULED_PAID_RUNS`` / ``ALGENT_SCHEDULED_PAID_RUNS``);
2. this machine holds the runner claim. Stricter than the interactive guard, which fails open: an unattended
   job that cannot PROVE it is the runner does not run;
3. no spend halt stands for today (the watchdog's day ceiling).

A failed run is retried once after ``flags.SCHEDULED_RETRY_DELAY_MIN`` minutes, only when the output marks the
failure transient (a network or provider hiccup), never for a code error or a watchdog kill, and only if 1-3 still
hold. A retry is the same command: the daily reuses its saved research, so nothing is bought twice.

Every job ends with one line in ``~/ops-log.md`` (who = ``scheduler``) and a record in
``runs_data/scheduler.jsonl`` (what ``newsroom doctor`` reads for the ``schedule`` check). The child's output goes
to the journal and to ``~/runlogs/<job>-<date>.log``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import flags

SITE = "https://www.ohmega.monster"
_KILLED_RC = (-15, -9, 143, 137)        # SIGTERM / SIGKILL as a child's return code (raw and shell-style)


@dataclass(frozen=True)
class Job:
    name: str
    argv: tuple[str, ...]               # after `python -m algent_backend.cli newsroom`
    utc: str                            # HH:MM the timer fires
    what: str


def jobs() -> dict[str, Job]:
    """The paid jobs. Edition times come from the daily's own flags so there is one place to change them."""
    from algent_backend.agent_system.agents.intel import flags as intel_flags

    out = {"menu": Job("menu", ("run", "--to", "menu"), flags.MENU_UTC, "newsroom menu")}
    for e in intel_flags.EDITIONS:
        # Refresh of instruments/statements happens before edition 1 only (the CLI skips it for later parts: their
        # collectors already run on timers).
        out[f"daily-{e.n}"] = Job(f"daily-{e.n}", ("intel", "daily", "--domain", "geopolitics", "--research",
                                                  "--edition", str(e.n)), e.utc, f"geopolitics daily, part {e.n} ({e.label})")
    return out


def paid_runs_enabled() -> bool:
    raw = os.environ.get("ALGENT_SCHEDULED_PAID_RUNS")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() not in ("0", "false", "no", "off")
    return bool(flags.SCHEDULED_PAID_RUNS)


def classify_failure(rc: int, tail: str) -> str:
    """'transient' (worth one retry), or why not: 'killed', 'code', 'unknown'. Unknown is NOT retried: a retry is
    spending, so it needs a positive reason."""
    if rc in _KILLED_RC:
        return "killed"
    low = tail.lower()

    def hit(markers: tuple[str, ...]) -> bool:
        return any(re.search(rf"\b{re.escape(m)}\b", low) for m in markers)

    if hit(flags.CODE_ERROR_MARKERS):
        return "code"
    return "transient" if hit(flags.TRANSIENT_MARKERS) else "unknown"


# ── everything that touches the world (tests substitute these) ────────────────────────────────
class Probes:
    def editions_done(self, day: str) -> set[int]:
        """Which parts of today's geopolitics daily already exist (empty when there is no record yet)."""
        import json as _json

        from algent_backend.agent_system.agents.intel.daily import daily_dir

        path = daily_dir("geopolitics") / f"{day}.json"
        try:
            record = _json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return set()
        done = {int(e.get("n", 0)) for e in record.get("editions") or [] if isinstance(e, dict)}
        return done or {1}            # a record from before editions existed is a part 1

    def runner_status(self) -> dict[str, Any]:
        from algent_backend.data_backup import runner

        return runner.status()

    def halted(self) -> bool:
        from algent_backend.agent_system.foundation import live_spend

        return live_spend.halt_path().exists() and json.loads(
            live_spend.halt_path().read_text(encoding="utf-8")).get("day") == live_spend.today()

    def day_spend(self) -> float:
        from . import watchdog

        return watchdog.day_spend()

    def run_child(self, job: Job, log: Path) -> tuple[int, str]:
        """Run the job's command, streaming its output to stdout (the journal) and ``log``; returns (rc, tail)."""
        log.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "algent_backend.cli", "newsroom", *job.argv]
        tail: list[str] = []
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"\n=== {datetime.now(UTC).isoformat(timespec='seconds')} {' '.join(cmd[3:])}\n")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", start_new_session=True)
            assert proc.stdout is not None
            for line in proc.stdout:
                print(line, end="", flush=True)
                fh.write(line)
                tail.append(line)
                del tail[:-flags.OUTCOME_TAIL_LINES]
            rc = proc.wait()
        return rc, "".join(tail)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def home(self) -> Path:
        return Path.home()

    def now(self) -> datetime:
        return datetime.now(UTC)


def journal_path() -> Path:
    from algent_backend.agent_system.foundation import live_spend

    return live_spend.halt_path().parent / "scheduler.jsonl"


def _record(event: dict[str, Any]) -> None:
    event = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), **event}
    try:
        p = journal_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        pass


def _ops_log(probes: Probes, line: str) -> None:
    stamp = probes.now().strftime("%Y-%m-%dT%H:%MZ")
    try:
        with (probes.home() / "ops-log.md").open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {stamp} · scheduler\n- {line}\n")
    except OSError:
        pass


def _link(job: Job, day: str) -> str:
    return f"{SITE}/geopolitics/{day}" if job.name.startswith("daily") else "backend/runs_data/menu_latest.md"


def _may_spend(probes: Probes) -> str:
    """'' when the job may run now, else the reason it may not."""
    if not paid_runs_enabled():
        return "paused (SCHEDULED_PAID_RUNS is off)"
    try:
        st = probes.runner_status()
    except Exception as exc:  # noqa: BLE001 - cannot prove it: do not spend
        return f"cannot check the runner claim ({type(exc).__name__})"
    if not st.get("reachable"):
        return "runner claim unreachable (archive down): an unattended paid run does not guess"
    if not st.get("is_runner"):
        return f"not the runner (claim held by {st.get('runner') or 'nobody'}; this machine is {st.get('this_host')})"
    try:
        if probes.halted():
            return "today's spend halt stands (newsroom watchdog --clear-halt lifts it)"
    except Exception:  # noqa: BLE001 - an unreadable marker must not block; the budget gate still refuses spend
        pass
    return ""


def run_job(name: str, probes: Probes | None = None) -> int:
    """Run one scheduled paid job (see module doc). Exit code: 0 published or skipped by policy, 1 failed."""
    probes = probes or Probes()
    job = jobs().get(name)
    if job is None:
        print(json.dumps({"error": f"unknown job {name!r}; one of {', '.join(jobs())}"}))
        return 2
    day = probes.now().strftime("%Y-%m-%d")
    log = probes.home() / "runlogs" / f"{job.name}-{day}.log"
    # Part 2 appends to part 1; run before it (a late or failed morning, a catch-up timer after a reboot) it would
    # become the day's whole report and a late part 1 would then overwrite it. So part 2 waits for part 1.
    if job.name == "daily-2" and 1 not in probes.editions_done(day):
        outcome = {"job": job.name, "outcome": "skipped", "why": "part 1 of today's daily does not exist yet"}
        _record(outcome)
        _ops_log(probes, f"{job.name}: skipped, part 1 of today's daily does not exist yet")
        print(json.dumps(outcome))
        return 0
    attempts: list[dict[str, Any]] = []
    for attempt in (1, 2):
        if why := _may_spend(probes):
            outcome = {"job": job.name, "outcome": "skipped", "why": why, "attempts": len(attempts)}
            _record(outcome)
            _ops_log(probes, f"{job.name}: skipped, {why}" + (f" (after a failed first attempt: {attempts[-1]['why']})"
                                                             if attempts else ""))
            print(json.dumps(outcome))
            return 1 if attempts else 0
        before = probes.day_spend()
        rc, tail = probes.run_child(job, log)
        spent = round(max(0.0, probes.day_spend() - before), 2)
        if rc == 0:
            spent = round(spent + sum(a["usd"] for a in attempts), 2)      # a retried run reports both attempts
            outcome = {"job": job.name, "outcome": "published", "usd": spent, "attempts": attempt, "log": str(log)}
            _record(outcome)
            _ops_log(probes, f"{job.name}: published, ${spent:.2f} spent (settled), {_link(job, day)}; log {log}")
            print(json.dumps(outcome))
            return 0
        kind = classify_failure(rc, tail)
        attempts.append({"rc": rc, "why": f"exit {rc}, {kind}", "usd": spent})
        if kind == "transient" and attempt == 1:
            print(json.dumps({"job": job.name, "retry_in_min": flags.SCHEDULED_RETRY_DELAY_MIN, "after": attempts[-1]}))
            probes.sleep(flags.SCHEDULED_RETRY_DELAY_MIN * 60)
            continue
        break
    total = round(sum(a["usd"] for a in attempts), 2)
    outcome = {"job": job.name, "outcome": "failed", "usd": total, "attempts": len(attempts),
               "why": attempts[-1]["why"], "retried": len(attempts) > 1, "log": str(log)}
    _record(outcome)
    _ops_log(probes, f"{job.name}: FAILED ({outcome['why']}{', retried once' if outcome['retried'] else ', not retried'}), "
                     f"${total:.2f} spent (settled); log {log}")
    print(json.dumps(outcome))
    return 1


def last_outcome(name: str) -> dict[str, Any] | None:
    """The newest scheduler record for ``name``, or None."""
    try:
        lines = journal_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("job") == name:
            return row
    return None
