"""
``newsroom watchdog`` — a hard floor against runaway API bills that needs no agent awake.

One pass (run by the ``ohmega-watchdog`` timer every 2 minutes): find running algent CLI processes, and stop
any that has run too long or spent too much. Spends nothing itself (no model call, no network).

Spend signal: ``agent_system/foundation/live_spend.py`` — each process writes its cumulative settled model/tool
spend to ``runs_data/live_spend/<day>__<pid>.json`` as the cost ledger is charged (throttled to ~3 s). Blind spots:
  * only *settled* charges, so the one call in flight is not counted (bounded by the article hard cap);
  * only spend routed through ``cost.add``/``settle`` — a provider call that bypasses the ledger is invisible,
    and so is spend by external harness CLIs (codex/grok) billed outside this process;
  * a process killed between throttled writes can under-report by a few seconds of spend;
  * a process that never charges (hung before spending) shows $0 — the wall-clock limit is the backstop.
The day total sums today's heartbeat files, including those of finished processes.

Day-level kill switch: past ``MAX_USD_PER_DAY`` the watchdog kills every paid process and writes
``runs_data/spend_halt.json``; ``cost.try_reserve`` refuses all billable work until the UTC day rolls over or
``newsroom watchdog --clear-halt``. Every action is appended to ``runs_data/watchdog.jsonl``.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.agent_system.foundation import live_spend

from . import flags

_CLI_MARK = "algent_backend.cli"


@dataclass(frozen=True)
class Proc:
    pid: int
    elapsed_s: float
    args: str


class Probes:
    """Everything that touches the world. Defaults are real; tests override methods."""

    def processes(self) -> list[Proc]:
        if sys.platform == "win32":
            return []          # the server is Linux; nothing to watch on a dev laptop
        out = subprocess.run(["ps", "-eo", "pid=,etimes=,args="], capture_output=True, text=True, timeout=15).stdout
        procs = []
        for line in out.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                procs.append(Proc(int(parts[0]), float(parts[1]), parts[2]))
        return procs

    def alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def signal(self, pid: int, sig: str) -> None:
        s = signal.SIGTERM if sig == "TERM" else getattr(signal, "SIGKILL", signal.SIGTERM)
        try:
            os.killpg(pid, s)
        except (OSError, AttributeError):
            os.kill(pid, s)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def watched(procs: list[Proc], self_pid: int | None = None) -> list[Proc]:
    """Algent CLI processes that can spend: not ourselves, not a free subcommand."""
    me = os.getpid() if self_pid is None else self_pid
    out = []
    for p in procs:
        if p.pid == me or _CLI_MARK not in p.args:
            continue
        tail = p.args.split(_CLI_MARK, 1)[1]
        if any(f" {w}" in f" {tail}" for w in flags.FREE_COMMANDS):
            continue
        out.append(p)
    return out


def limit_minutes(args: str) -> int:
    for key, minutes in flags.MAX_MINUTES.items():
        if key != "default" and all(w in args for w in key.split()):
            return minutes
    return flags.MAX_MINUTES["default"]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def process_spend(proc: Proc, now: float) -> float:
    """Today's heartbeat for this pid, ignoring a file left by an earlier process that reused the pid."""
    row = _read_json(live_spend.live_dir() / f"{live_spend.today()}__{proc.pid}.json")
    if row and float(row.get("started") or 0) >= now - proc.elapsed_s - 120:
        return float(row.get("usd") or 0.0)
    return 0.0


def day_spend() -> float:
    d = live_spend.live_dir()
    if not d.is_dir():
        return 0.0
    return round(sum(float(_read_json(f).get("usd") or 0.0) for f in d.glob(f"{live_spend.today()}__*.json")), 6)


def _prune_heartbeats() -> None:
    d = live_spend.live_dir()
    if not d.is_dir():
        return
    cutoff = (datetime.now(UTC) - timedelta(days=flags.LIVE_SPEND_KEEP_DAYS)).strftime("%Y-%m-%d")
    for f in d.glob("*__*.json"):
        if f.name.split("__", 1)[0] < cutoff:
            f.unlink(missing_ok=True)


def log_path() -> Path:
    return live_spend.halt_path().parent / "watchdog.jsonl"


def _log(event: dict[str, Any]) -> None:
    event = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), **event}
    print(json.dumps(event))
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        pass


def _stop(proc: Proc, reason: str, probes: Probes, dry_run: bool, usd: float) -> None:
    event = {"action": "would_kill" if dry_run else "kill", "pid": proc.pid, "reason": reason,
             "elapsed_min": round(proc.elapsed_s / 60, 1), "usd": round(usd, 4), "cmd": proc.args[:120]}
    if not dry_run:
        probes.signal(proc.pid, "TERM")
        probes.sleep(flags.KILL_GRACE_S)
        if probes.alive(proc.pid):
            probes.signal(proc.pid, "KILL")
            event["escalated"] = "SIGKILL"
    _log(event)


def run_pass(probes: Probes | None = None, *, dry_run: bool = False, now: float | None = None) -> dict[str, Any]:
    probes = probes or Probes()
    now = time.time() if now is None else now
    procs = watched(probes.processes())
    day_usd = day_spend()
    result: dict[str, Any] = {"watched": len(procs), "day_usd": day_usd, "killed": [], "halted": False}
    day_over = day_usd > flags.MAX_USD_PER_DAY
    for p in procs:
        usd = process_spend(p, now)
        reason = None
        if day_over:
            reason = f"day spend ${day_usd:.2f} over ${flags.MAX_USD_PER_DAY:.2f}"
        elif usd > flags.MAX_USD_PER_RUN:
            reason = f"run spend ${usd:.2f} over ${flags.MAX_USD_PER_RUN:.2f}"
        elif p.elapsed_s > limit_minutes(p.args) * 60:
            reason = f"ran {p.elapsed_s / 60:.0f} min, over {limit_minutes(p.args)} min"
        if reason:
            _stop(p, reason, probes, dry_run, usd)
            result["killed"].append(p.pid)
    if day_over:
        result["halted"] = True
        if not dry_run and not live_spend.halt_path().exists():
            live_spend.halt_path().write_text(json.dumps(
                {"day": live_spend.today(), "usd": day_usd, "limit": flags.MAX_USD_PER_DAY,
                 "at": datetime.now(UTC).isoformat(timespec="seconds")}), encoding="utf-8")
        _log({"action": "would_halt" if dry_run else "halt", "day_usd": day_usd, "limit": flags.MAX_USD_PER_DAY})
    if not dry_run:
        _prune_heartbeats()
    if not result["killed"] and not day_over:
        _log({"action": "pass", "watched": len(procs), "day_usd": day_usd, "dry_run": dry_run})
    return result


def clear_halt() -> bool:
    existed = live_spend.halt_path().exists()
    live_spend.halt_path().unlink(missing_ok=True)
    _log({"action": "clear_halt", "existed": existed})
    return existed


def last_pass_age_minutes() -> float | None:
    """Minutes since the last logged pass, or None if the log is missing/empty."""
    try:
        last = log_path().read_text(encoding="utf-8").strip().splitlines()[-1]
        ts = datetime.fromisoformat(json.loads(last)["ts"])
    except (OSError, IndexError, ValueError, KeyError):
        return None
    return (datetime.now(UTC) - ts).total_seconds() / 60
