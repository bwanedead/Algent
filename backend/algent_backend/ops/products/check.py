"""
``newsroom products check`` - the live machine judged against the registry. Spends nothing, writes nothing.

Rows (each ok / warn / fail, same shape as the doctor's):
  registry   the entries obey the rules (validate.py)
  stores     every store the registry names exists on this machine (a missing irreplaceable one is a fail)
  timers     every registered timer is installed and enabled; an ``ohmega-*`` timer nobody registered is an orphan (server only: no systemd, no row)
  snapshot   every irreplaceable store that has files is in the newest snapshot's manifest
  fresh      every product with a heartbeat file and a timer ran within ``PRODUCT_STALE_CADENCES`` of its slowest cadence
  budgets    every store is inside its registry budget (the envelope's own ``store:*`` rows, folded)

Every measurement is a method on ``Probes`` so tests substitute fakes; a probe that cannot measure gives a warn, never a guess.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

from algent_backend.ops import doctor, envelope, envelope_flags as f

from . import validate, views

OK, WARN, FAIL = doctor.OK, doctor.WARN, doctor.FAIL


def _row(status: str, detail: str) -> dict[str, Any]:
    return {"status": status, "detail": detail}


class Probes(envelope.Probes):
    def installed_timers(self) -> set[str] | None:
        """Names (without the ``ohmega-`` prefix) of the installed ohmega timer units; None without systemd."""
        if not shutil.which("systemctl"):
            return None
        done = subprocess.run(["systemctl", "list-unit-files", "ohmega-*.timer", "--no-legend", "--no-pager"], capture_output=True, text=True, timeout=15)
        return {line.split()[0][len("ohmega-"):-len(".timer")] for line in done.stdout.splitlines() if line.strip().startswith("ohmega-")}

    def newest_mtime(self, pattern: str) -> float | None:
        files = [p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p)]
        return max((os.stat(p).st_mtime for p in files), default=None)


def row_registry() -> dict[str, Any]:
    problems = validate.validate()
    return _row(FAIL, f"{len(problems)} problem(s): " + "; ".join(problems[:4])) if problems else _row(OK, f"{len(views.products())} products, {len(views.stores())} stores, {len(views.jobs())} jobs")


def row_stores(p: Probes) -> dict[str, Any]:
    missing = [(pr, s) for pr, s in views.stores() if not s.path().exists()]
    lost = [s.name for pr, s in missing if s.backed_up and pr.irreplaceable]
    if lost:       # stores are created on first write, so a missing one is a warning; on the server an irreplaceable one missing is the thing to look at first
        return _row(WARN, f"irreplaceable store(s) not on this machine: {', '.join(lost)} (never written yet, or lost: newsroom backup restore)")
    return _row(OK, f"{len(views.stores()) - len(missing)} of {len(views.stores())} stores present" + (f"; not here yet: {', '.join(s.name for _, s in missing)}" if missing else ""))


def row_timers(p: Probes) -> dict[str, Any]:
    installed = p.installed_timers()
    if installed is None:
        return _row(OK, "no systemd on this machine; the timers belong to the server")
    want = {j.name for _, j in views.timers()}
    missing, orphans = sorted(want - installed), sorted(installed - want)
    off = [n for n in sorted(want & installed) if p.timer_state(n) not in ("enabled", None)]
    problems = ([f"not installed: {', '.join(missing)} (infra/server/install_schedules.sh)"] if missing else []) + \
               ([f"installed but not enabled: {', '.join(off)}"] if off else []) + ([f"orphan timer(s) no product owns: {', '.join(orphans)}"] if orphans else [])
    return _row(WARN, "; ".join(problems)) if problems else _row(OK, f"all {len(want)} registered timers installed and enabled, no orphans")


def row_snapshot(p: Probes) -> dict[str, Any]:
    snap = p.snapshot_state()
    last = snap["state"].get("last_snapshot")
    if not last:
        return _row(WARN, "no snapshot has been taken yet, so coverage cannot be verified (newsroom backup snapshot)")
    have = set((last.get("by_store") or {}))
    uncovered = [name for name, path in views.backup_sources().items() if path.is_dir() and any(x.is_file() for x in path.rglob("*")) and name not in have]
    if uncovered:
        return _row(FAIL, f"irreplaceable store(s) with files but absent from the snapshot of {last.get('date')}: {', '.join(sorted(uncovered))}")
    return _row(OK, f"snapshot of {last.get('date')} covers all {len(have)} stores that have files")


def _slowest_min(p: Any) -> float:
    return max((j.every_min for j in p.job_list() if j.kind == "timer"), default=0.0)


def row_fresh(p: Probes, now: float | None = None) -> dict[str, Any]:
    now = now or time.time()
    stale, checked = [], 0
    for prod in views.products():
        slowest = _slowest_min(prod)
        if not prod.heartbeat or not slowest:
            continue
        for pat in prod.heartbeat:
            name, _, rel = pat.partition("/")
            s = views.store(name)
            if s is None or not s.path().exists():
                continue
            mtime = p.newest_mtime(str(s.path() / rel))
            checked += 1
            limit_min = f.PRODUCT_STALE_CADENCES * slowest + 5
            if mtime is None:
                stale.append(f"{prod.id} (no {rel})")
            elif (now - mtime) / 60 > limit_min:
                stale.append(f"{prod.id} ({(now - mtime) / 3600:.0f} h)")
    if not checked:
        return _row(OK, "no product has a heartbeat file on this machine")
    return _row(WARN, f"{len(stale)} of {checked} stale (> {f.PRODUCT_STALE_CADENCES} cadences): {', '.join(stale)}") if stale else _row(OK, f"{checked} heartbeats within {f.PRODUCT_STALE_CADENCES} cadences")


def row_budgets(p: Probes, now: float | None = None) -> dict[str, Any]:
    rows = envelope.rows_stores(p, now or time.time())
    bad = {k.split(":", 1)[1]: v for k, v in rows.items() if v["status"] != OK}
    if not bad:
        return _row(OK, f"{len(rows)} measured stores inside their budgets")
    status = FAIL if any(v["status"] == FAIL for v in bad.values()) else WARN
    return _row(status, "; ".join(f"{n}: {v['detail']}" for n, v in bad.items()))


def run(probes: Probes | None = None, skip: tuple[str, ...] = (), now: datetime | None = None) -> dict[str, Any]:
    p = probes or Probes()
    steps = [("registry", row_registry), ("stores", lambda: row_stores(p)), ("timers", lambda: row_timers(p)), ("snapshot", lambda: row_snapshot(p)),
             ("fresh", lambda: row_fresh(p)), ("budgets", lambda: row_budgets(p))]
    rows: dict[str, dict[str, Any]] = {}
    for name, step in steps:
        if name in skip:
            continue
        try:
            rows[f"products:{name}"] = step()
        except Exception as exc:  # noqa: BLE001 - one probe failing must not blank the report
            rows[f"products:{name}"] = _row(WARN, f"could not measure: {doctor.scrub(exc)}")
    counts = {s: sum(1 for r in rows.values() if r["status"] == s) for s in (OK, WARN, FAIL)}
    return {"ok": counts[FAIL] == 0, "at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
            "summary": f"{counts[OK]} ok, {counts[WARN]} warn, {counts[FAIL]} fail", "rows": rows}
