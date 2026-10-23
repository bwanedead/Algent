"""
``newsroom envelope`` - every row of the operating-envelope register (docs/architecture/foundation.md, sections 2-3), measured live and
judged ok / warn / fail against the budgets in ``envelope_flags.py``. Spends nothing and writes nothing but a small state file (daily
spend, so a month total survives the heartbeat files' three-day retention). The doctor embeds the rows it does not already have.

Rows: disk, memory, journald, store:<name> (size + 7-day written; budgets from the product registry), r2, backup, restore_drill, feeds, search, site (the last
smoke test of the production site), spend_day, spend_month.
Every measurement is a method on ``Probes`` so tests substitute fakes; a probe that cannot measure returns None and its row says "unknown"
(warn), never a guess.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.ops import doctor, envelope_flags as f, opslog
from algent_backend.ops.products import views

OK, WARN, FAIL = doctor.OK, doctor.WARN, doctor.FAIL
_MB = 1024 * 1024


def _row(status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, **extra}


def _band(value: float, warn: float, fail: float, *, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        return FAIL if value >= fail else WARN if value >= warn else OK
    return FAIL if value < fail else WARN if value < warn else OK


class Probes(doctor.Probes):
    """What touches the world, on top of the doctor's disk / memory / search probes."""

    def disk(self) -> tuple[float, float]:
        du = shutil.disk_usage(Path(__file__).resolve().parents[3])
        return du.free / 1e9, du.total / 1e9

    def journal_mb(self) -> float | None:
        """Journal disk use. `journalctl --disk-usage` prints "... take up 562.0M in the file system."; a box without journald returns None."""
        if not shutil.which("journalctl"):
            return None
        try:
            done = subprocess.run(["journalctl", "--disk-usage"], capture_output=True, text=True, timeout=15)
            m = re.search(r"([\d.]+)\s*([KMGT])", done.stdout)
            return float(m.group(1)) * {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0 ** 2}[m.group(2)] if m else None
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    def store_roots(self) -> dict[str, Path]:
        """Every budgeted store on this machine by name: the product registry's stores (ops/products), the single list of what we keep."""
        from algent_backend.ops.products import views

        return views.store_roots()

    def store_stats(self, root: Path, now: float) -> tuple[int, int] | None:
        """(bytes, bytes written in the last 7 days) of one directory tree; None when it does not exist here."""
        if not root.exists():
            return None
        total = recent = 0
        horizon = now - 7 * 86400
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                try:
                    st = os.stat(os.path.join(dirpath, name))
                except OSError:
                    continue
                total += st.st_size
                if st.st_mtime >= horizon:
                    recent += st.st_size
        return total, recent

    def r2_status(self) -> dict[str, Any] | None:
        from algent_backend.publishing import object_budget, object_store

        return object_budget.meter().status() if object_store.configured() else None

    def snapshot_state(self) -> dict[str, Any]:
        from algent_backend.data_backup import snapshot

        return {"state": snapshot.read_state(), "age_h": snapshot.age_hours(), "drill_age_days": snapshot.drill_age_days()}

    def feed_rows(self) -> list[dict[str, Any]]:
        from algent_backend.live import runner

        return runner.doctor_rows()

    def feed_cadence_min(self, feed: str) -> float:
        from algent_backend.live import flags as live_flags

        return live_flags.CADENCE_MINUTES.get(feed, live_flags.AIS_FLUSH_SECONDS / 60)

    def search_results(self, base: str) -> int:
        payload = self.http_get_json(f"{base.rstrip('/')}/search?q=ohmega&format=json")
        return len(payload.get("results") or [])

    def spend_by_day(self) -> dict[str, float]:
        """USD by UTC day from the watchdog heartbeats (kept three days); the envelope state carries them past that."""
        from algent_backend.agent_system.foundation import live_spend

        out: dict[str, float] = {}
        d = live_spend.live_dir()
        for p in d.glob("*__*.json") if d.is_dir() else ():
            try:
                out[p.name.split("__", 1)[0]] = out.get(p.name.split("__", 1)[0], 0.0) + float(json.loads(p.read_text(encoding="utf-8")).get("usd") or 0.0)
            except (OSError, ValueError):
                continue
        return out

    def smoke_state(self) -> dict[str, Any]:
        """The last production smoke report (ops/smoke/state.py), {} when none was ever recorded."""
        from algent_backend.ops.smoke import state

        return state.read()

    def state_path(self) -> Path:
        from algent_backend.agent_system.foundation import live_spend

        return live_spend.halt_path().parent / "envelope_state.json"


# ── rows ─────────────────────────────────────────────────────────────────────────────────────────
def _gb(x: float) -> str:
    return f"{x:.1f} GB"


def row_disk(p: Probes) -> dict[str, Any]:
    free, total = p.disk()
    return _row(_band(free, f.DISK_FREE_GB[1], f.DISK_FREE_GB[0], higher_is_worse=False), f"{_gb(free)} free of {_gb(total)}",
                value=round(free, 1), budget=f"warn < {f.DISK_FREE_GB[1]:.0f} GB, fail < {f.DISK_FREE_GB[0]:.0f} GB free")


def row_memory(p: Probes) -> dict[str, Any]:
    mb = p.mem_available_mb()
    if mb is None:
        return _row(WARN, "unknown")
    return _row(_band(mb, f.MEM_AVAILABLE_MB[1], f.MEM_AVAILABLE_MB[0], higher_is_worse=False), f"{mb:.0f} MB available",
                value=round(mb), budget=f"warn < {f.MEM_AVAILABLE_MB[1]:.0f} MB, fail < {f.MEM_AVAILABLE_MB[0]:.0f} MB")


def row_journal(p: Probes) -> dict[str, Any]:
    mb = p.journal_mb()
    if mb is None:
        return _row(WARN, "unknown (no journald, or not readable by this user)")
    return _row(_band(mb, *f.JOURNAL_MB), f"{mb:.0f} MB", value=round(mb), budget=f"warn > {f.JOURNAL_MB[0]:.0f} MB, fail > {f.JOURNAL_MB[1]:.0f} MB (cap 200 MB: infra/server/journald-ohmega.conf)")


def rows_stores(p: Probes, now: float) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, root in p.store_roots().items():
        got = p.store_stats(root, now)
        if got is None:
            continue
        size, recent = got[0] / _MB, got[1] / _MB
        b = views.budget_for(name)
        warn, fail, grow = (b.warn_mb, b.fail_mb, b.written_mb) if b else f.DEFAULT_STORE_MB
        status = FAIL if size >= fail else WARN if size >= warn or recent >= grow else OK
        out[f"store:{name}"] = _row(status, f"{size:,.0f} MB, {recent:,.0f} MB written in 7 d", mb=round(size, 1), written_7d_mb=round(recent, 1),
                                    budget=f"size warn {warn} / fail {fail} MB, written warn {grow} MB")
    return out


def row_r2(p: Probes) -> dict[str, Any]:
    rep = p.r2_status()
    if rep is None:
        return _row(WARN, "object store not configured on this machine")
    a, b, s = (rep["usage"][k] for k in ("class_a", "class_b", "storage_bytes"))
    status = FAIL if rep["level"] == "stop" else WARN if rep["level"] == "warn" else OK
    return _row(status, f"{rep['month']}: class A {a['share']:.1%} (projected {a['projected_share']:.0%}), class B {b['share']:.1%}, stored {s['used'] / 1024 ** 3:.2f} GB ({s['share']:.0%})",
                value=max(a["share"], s["share"]), budget="warn 70%, hard stop 90% of the free tier (database/flags.py)")


def row_backup(p: Probes) -> dict[str, Any]:
    snap = p.snapshot_state()
    age = snap["age_h"]
    fail = (snap["state"].get("last_snapshot_failure") or {}).get("error")
    if age is None:
        return _row(FAIL, "no snapshot has ever been taken (newsroom backup snapshot)" + (f"; last failure: {fail}" if fail else ""))
    return _row(_band(age, *f.SNAPSHOT_AGE_H), f"newest snapshot {age:.0f} h old ({snap['state']['last_snapshot'].get('date')}, {snap['state']['last_snapshot'].get('files')} files)",
                value=round(age, 1), budget=f"warn > {f.SNAPSHOT_AGE_H[0]:.0f} h, fail > {f.SNAPSHOT_AGE_H[1]:.0f} h")


def row_drill(p: Probes) -> dict[str, Any]:
    snap = p.snapshot_state()
    drill = snap["state"].get("last_drill")
    if not drill:
        return _row(WARN, "no restore drill has been run (newsroom backup restore-drill)")
    if not drill.get("ok"):
        return _row(FAIL, f"last restore drill FAILED: {'; '.join(drill.get('problems') or []) or drill.get('note') or 'see ~/ops-log.md'}")
    age = snap["drill_age_days"] or 0.0
    return _row(WARN if age > f.DRILL_AGE_DAYS else OK, f"restore drill ok {age:.0f} d ago ({drill.get('snapshot')}, {drill.get('files')} files verified)",
                value=round(age, 1), budget=f"stale > {f.DRILL_AGE_DAYS:.0f} d")


def row_feeds(p: Probes, env: dict[str, str], now: datetime | None = None) -> dict[str, Any]:
    now, stale, live = now or datetime.now(UTC), [], 0
    for r in p.feed_rows():
        if r["needs"]:
            continue                                            # no key: not a fault of the box
        live += 1
        if not r["last_ok"]:
            stale.append(f"{r['feed']} (never)")
            continue
        age = (now - datetime.fromisoformat(r["last_ok"])).total_seconds() / 60
        if age > f.FEED_STALE_CADENCES * p.feed_cadence_min(r["feed"]) + 5:
            stale.append(f"{r['feed']} ({age:.0f} min)")
    if not stale:
        return _row(OK, f"{live} feeds fresh", value=0, budget=f"stale after {f.FEED_STALE_CADENCES} cadences + 5 min")
    status = FAIL if live and len(stale) / live >= f.FEED_FAIL_SHARE else WARN
    return _row(status, f"{len(stale)} of {live} stale: {', '.join(stale[:6])}", value=len(stale), budget=f"fail at {f.FEED_FAIL_SHARE:.0%} of feeds")


def row_search(p: Probes, env: dict[str, str]) -> dict[str, Any]:
    base = env.get("ALGENT_SEARXNG_URL") or "http://127.0.0.1:8080"
    try:
        n = p.search_results(base)
    except Exception as exc:  # noqa: BLE001
        return _row(WARN, f"SearXNG not reachable: {doctor.scrub(exc, env)}")
    return _row(FAIL if n == 0 else WARN if n < f.SEARCH_MIN_RESULTS else OK, f"{n} results for the probe query", value=n,
                budget=f"warn < {f.SEARCH_MIN_RESULTS}, fail at 0")


def row_site(p: Probes, now: datetime) -> dict[str, Any]:
    """The hourly smoke test of the production site (``newsroom site smoke --log``): failing is a fail, a run that stopped happening is a warning."""
    from algent_backend.ops.smoke import flags as smoke_flags, state

    st = p.smoke_state()
    if not st:
        return _row(WARN, "no site smoke test has been recorded (newsroom site smoke --log; the hourly site-smoke job)")
    age = state.age_hours(st, now)
    if not st.get("ok"):
        return _row(FAIL, f"site smoke FAILING since {st.get('since_failure')}: " + "; ".join(st.get("failing") or [])[:300], value=len(st.get("failing") or []),
                    budget="fail on any failed check (ops/smoke)")
    if age is None or age > smoke_flags.STATE_STALE_H:
        return _row(WARN, f"last site smoke test {'unreadable' if age is None else f'{age:.1f} h ago'} (hourly job)", value=round(age or 0, 1),
                    budget=f"warn > {smoke_flags.STATE_STALE_H:g} h")
    return _row(OK, f"{st.get('summary')} ({age:.1f} h ago)", value=round(age, 1), budget=f"warn > {smoke_flags.STATE_STALE_H:g} h old or any failed check")


def rows_spend(p: Probes, now: datetime) -> dict[str, dict[str, Any]]:
    from algent_backend.ops import flags as ops_flags

    days = p.spend_by_day()
    path = p.state_path()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    kept = {d: max(float(state.get("spend_days", {}).get(d, 0.0)), usd) for d, usd in {**state.get("spend_days", {}), **days}.items()}
    kept = dict(sorted(kept.items())[-62:])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"spend_days": kept}, indent=1), encoding="utf-8")
    except OSError:
        pass
    today, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    day_usd = kept.get(today, 0.0)
    month_usd = sum(v for d, v in kept.items() if d.startswith(month))
    ceiling = ops_flags.MAX_USD_PER_DAY
    return {
        "spend_day": _row(_band(day_usd, f.SPEND_DAY_WARN_SHARE * ceiling, ceiling), f"${day_usd:.2f} today (settled)", value=round(day_usd, 2),
                          budget=f"warn > ${f.SPEND_DAY_WARN_SHARE * ceiling:.0f}, fail > ${ceiling:.0f} (the watchdog's halt)"),
        "spend_month": _row(_band(month_usd, *f.SPEND_MONTH_USD), f"${month_usd:.2f} this month (settled, from {len([d for d in kept if d.startswith(month)])} recorded days)",
                            value=round(month_usd, 2), budget=f"warn > ${f.SPEND_MONTH_USD[0]:.0f}, fail > ${f.SPEND_MONTH_USD[1]:.0f}"),
    }


# ── the report ───────────────────────────────────────────────────────────────────────────────────
def run(env: dict[str, str] | None = None, probes: Probes | None = None, now: datetime | None = None,
        skip: tuple[str, ...] = ()) -> dict[str, Any]:
    """Measure every row. ``skip`` names rows to leave out (the doctor already has some). A row that raises is a warn, never a crash."""
    env = dict(os.environ if env is None else env)
    p = probes or Probes()
    now = now or datetime.now(UTC)
    steps: list[tuple[str, Any]] = [
        ("disk", lambda: row_disk(p)), ("memory", lambda: row_memory(p)), ("journald", lambda: row_journal(p)),
        ("stores", lambda: rows_stores(p, time.time())), ("r2", lambda: row_r2(p)), ("backup", lambda: row_backup(p)),
        ("restore_drill", lambda: row_drill(p)), ("feeds", lambda: row_feeds(p, env, now)), ("search", lambda: row_search(p, env)),
        ("site", lambda: row_site(p, now)), ("spend", lambda: rows_spend(p, now)),
    ]
    rows: dict[str, dict[str, Any]] = {}
    for name, step in steps:
        if name in skip:
            continue
        try:
            got = step()
            rows.update(got if name in ("stores", "spend") else {name: got})
        except Exception as exc:  # noqa: BLE001 - one probe failing must not blank the report
            rows[name] = _row(WARN, f"could not measure: {doctor.scrub(exc, env)}")
    counts = {s: sum(1 for r in rows.values() if r["status"] == s) for s in (OK, WARN, FAIL)}
    return {"ok": counts[FAIL] == 0, "at": now.isoformat(timespec="seconds"), "summary": f"{counts[OK]} ok, {counts[WARN]} warn, {counts[FAIL]} fail", "rows": rows}


def one_line(report: dict[str, Any]) -> str:
    """The daily ops-log line: the verdict, then every row that is not ok (or the headline numbers when all is well)."""
    rows = report["rows"]
    bad = [f"{r['status'].upper()} {name}: {r['detail']}" for name, r in rows.items() if r["status"] != OK]
    if bad:
        return f"envelope {report['summary']} - " + "; ".join(bad)
    head = [rows[k]["detail"] for k in ("disk", "memory", "r2", "backup", "spend_day") if k in rows]
    return f"envelope all {len(rows)} rows ok - " + "; ".join(head)


def log(report: dict[str, Any]) -> None:
    opslog.append("envelope", one_line(report))
