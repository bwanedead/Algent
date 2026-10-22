"""
``newsroom doctor`` — is THIS machine ready to be the runner? One JSON document, ok/warn/fail per check.

Spends nothing: no model call, no paid search, no paid read, no harness prompt. It touches the network only
for one free query per free engine (cached 10 minutes), one free page read, ``select 1`` on the database and a
``git ls-remote``. Secrets are reported by NAME only; any error text that could carry a connection string is
withheld (``scrub``). Every check is a method on ``Probes`` so tests substitute fakes for network, db and
subprocesses.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

OK, WARN, FAIL = "ok", "warn", "fail"

#: (label, alternatives — any one satisfies, severity if all missing). KEEP IN SYNC with docs/credentials.md
#: (a test asserts every name here appears in the manifest).
REQUIRED_KEYS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("house model key", ("META_MODEL_API_KEY",), FAIL),
    ("database (optional: Postgres publish flag)", ("DATABASE_URL",), WARN),
    ("gemini (hero images)", ("GEMINI_API_KEY", "GOOGLE_API_KEY"), WARN),
    ("x read", ("X_BEARER_TOKEN", "X_API_BEARER_TOKEN", "X_BEARER", "X_BEARER_KEY", "TWITTER_BEARER_TOKEN"), WARN),
    ("x post key", ("X_API_KEY",), WARN),
    ("x post key secret", ("X_API_KEY_SECRET",), WARN),
    ("x post access token", ("X_ACCESS_TOKEN",), WARN),
    ("x post access secret", ("X_ACCESS_TOKEN_SECRET",), WARN),
    ("x post handle", ("X_POST_HANDLE",), WARN),
)
#: Last-resort paid engines: absent just means that rung of the chain is skipped.
OPTIONAL_KEYS = ("TAVILY_API_KEY", "EXA_API_KEY", "BRAVE_API_KEY", "FIRECRAWL_API_KEY", "OPENAI_API_KEY",
                 "ANTHROPIC_API_KEY", "XAI_API_KEY")

_ENGINE_TTL_S = 600
_MIN_DISK_GB = (1.0, 5.0)      # fail below, warn below
_MIN_MEM_MB = 600


def scrub(text: object, env: dict[str, str] | None = None) -> str:
    """Error text safe to print: withheld entirely if it could hold a connection string, secret values redacted."""
    raw = str(text)
    if "postgres" in raw.lower() or "@" in raw:
        return "details withheld (may contain a connection string)"
    for k, v in (env or {}).items():
        if v and len(v) >= 8 and any(t in k for t in ("KEY", "TOKEN", "SECRET", "URL", "PASSWORD")):
            raw = raw.replace(v, "<redacted>")
    return raw[:160]


def _check(status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "detail": detail, **extra}


class Probes:
    """Everything that touches the world. Defaults are real; tests override methods."""

    def db_select1(self) -> None:
        import importlib

        # the package re-exports a function named `migrate`, which shadows the module on attribute import
        migrate = importlib.import_module("algent_backend.database.migrate")
        with migrate.connect() as conn:
            conn.execute("select 1")

    def db_budget(self) -> dict[str, Any]:
        """Database size vs the free-plan quota (``database/size.report``): a few catalog reads."""
        import importlib

        migrate = importlib.import_module("algent_backend.database.migrate")
        from algent_backend.database import size

        with migrate.connect() as conn:
            return size.report(conn, top=3)

    def http_get_json(self, url: str, timeout: float = 10.0) -> Any:
        import httpx

        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def engine_query(self, name: str) -> int:
        """One cheap query on a free engine; returns result count."""
        from algent_backend.agent_system.tools.sourcing.search import bing, ddg, gnews

        mod = {"ddg": ddg, "bing": bing, "gnews": gnews}[name]
        return len(mod.search("world news today", max_results=3))

    def playwright_importable(self) -> bool:
        return importlib.util.find_spec("playwright") is not None

    def free_read(self) -> dict[str, Any]:
        from algent_backend.agent_system.tools.sourcing.depth.fetch_content import _fetch

        return _fetch("https://example.com", allow_paid_fallback=False)

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(self, cmd: list[str], timeout: float = 20.0, cwd: Path | None = None) -> tuple[int, str]:
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout, cwd=cwd)
        return done.returncode, (done.stdout + done.stderr).strip()

    def basemap_loaded(self) -> bool:
        from algent_backend.agent_system.agents.intel import geo

        return bool(geo.load())

    def runner_status(self) -> dict[str, Any]:
        from algent_backend.data_backup import runner

        return runner.status()

    def quota_summary(self) -> dict[str, dict[str, int]]:
        from algent_backend.agent_system.tools.sourcing.search import quota

        return quota.summary()

    def watchdog_age_minutes(self) -> float | None:
        from algent_backend.ops import watchdog

        return watchdog.last_pass_age_minutes()

    def timer_state(self, job: str) -> str | None:
        """systemd's `is-enabled` word for the job's timer ("enabled", "disabled", "not-found"), None without systemd."""
        if not shutil.which("systemctl"):
            return None
        done = subprocess.run(["systemctl", "is-enabled", f"ohmega-{job}.timer"], capture_output=True, text=True, timeout=10)
        return (done.stdout or done.stderr).strip().splitlines()[0] if (done.stdout or done.stderr).strip() else "unknown"

    def scheduled_jobs(self) -> dict[str, dict[str, Any]]:
        """job -> {"utc", "last"} for the paid scheduled jobs (`ops/schedule.py`)."""
        from algent_backend.ops import schedule

        return {j.name: {"utc": j.utc, "last": schedule.last_outcome(j.name)} for j in schedule.jobs().values()}

    def scheduled_enabled(self) -> bool:
        from algent_backend.ops import schedule

        return schedule.paid_runs_enabled()

    def disk_free_gb(self) -> float:
        return shutil.disk_usage(Path(__file__).resolve().parents[3]).free / 1e9

    def mem_available_mb(self) -> float | None:
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024
        except OSError:
            pass
        try:
            import ctypes

            class _Mem(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                            ("avail", ctypes.c_ulonglong), ("tpf", ctypes.c_ulonglong),
                            ("apf", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong),
                            ("ave", ctypes.c_ulonglong)]

            m = _Mem()
            m.len = ctypes.sizeof(_Mem)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))   # type: ignore[attr-defined]
            return m.avail / 1048576
        except Exception:  # noqa: BLE001
            return None


def _engine_cache_path() -> Path:
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    return Path(runs_data_root()) / "doctor_engine_cache.json"


def _cached_engine(name: str, probes: Probes) -> tuple[bool, str]:
    """One request per engine per 10 minutes: the doctor is safe to run repeatedly."""
    path = _engine_cache_path()
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    hit = cache.get(name)
    if hit and time.time() - hit.get("ts", 0) < _ENGINE_TTL_S:
        return bool(hit["ok"]), f"{hit['detail']} (cached)"
    try:
        n = probes.engine_query(name)
        ok, detail = n > 0, f"answered, {n} result(s)" if n else "answered but empty"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"failed: {scrub(exc)}"
    try:
        cache[name] = {"ts": time.time(), "ok": ok, "detail": detail}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return ok, detail


def check_keys(env: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, names, severity in REQUIRED_KEYS:
        have = [n for n in names if env.get(n)]
        out[f"key:{label}"] = _check(OK, f"{have[0]} set") if have else _check(severity, f"missing: {' or '.join(names)}")
    missing = [n for n in OPTIONAL_KEYS if not env.get(n)]
    out["key:optional paid"] = _check(OK if not missing else WARN,
                                      "all set" if not missing else f"not set (rung skipped): {', '.join(missing)}")
    return out


def check_database(env: dict[str, str], probes: Probes) -> dict[str, Any]:
    from algent_backend.database import flags as db_flags

    needed = db_flags.postgres_publish()          # off by default: the server is the record and the site reads files in R2
    if not env.get("DATABASE_URL"):
        return {"database": _check(FAIL if needed else OK, "DATABASE_URL not set" + ("" if needed else " (not needed: Postgres publish flag is off)"))}
    try:
        probes.db_select1()
    except Exception as exc:  # noqa: BLE001
        return {"database": _check(FAIL if needed else WARN, f"not reachable: {scrub(exc, env)}" + ("" if needed else " (optional: Postgres publish flag is off)"))}
    return {"database": _check(OK, "connected, select 1 ok")}


def check_object_store(env: dict[str, str]) -> dict[str, Any]:
    """The published-file store (R2 by default) and its free-tier budget (publishing/object_budget.py): FAIL at the hard stop."""
    from algent_backend.database import flags as db_flags
    from algent_backend.publishing import object_budget, object_store

    if env.get("ALGENT_DB_PUBLISH", "1").strip().lower() in ("0", "false", "no", "off") or env.get("ALGENT_PUBLISH", "1").strip().lower() in ("0", "false", "no", "off"):
        return {"object store": _check(WARN, "publishing paused (ALGENT_DB_PUBLISH=0)")}
    backend = (env.get("ALGENT_OBJECT_BACKEND", "").strip().lower() or db_flags.OBJECT_BACKEND)
    if backend != "r2":
        return {"object store": _check(OK, f"backend {backend} (no R2 budget applies)")}
    missing = [n for n in object_store.R2_ENV if not env.get(n)]
    if missing:
        return {"object store": _check(FAIL, f"R2 not configured, missing: {', '.join(missing)} (docs/credentials.md)")}
    rep = object_budget.meter().status()
    a, b, s = (rep["usage"][k] for k in ("class_a", "class_b", "storage_bytes"))
    line = (f"R2 {rep['month']}: class A {a['used']:,}/{a['free_tier']:,} ({a['share']:.0%}, projected {a['projected_share']:.0%}), "
            f"class B {b['used']:,}, stored {s['used'] / 1024 ** 2:,.0f} MB ({s['share']:.0%})")
    status = FAIL if rep["level"] == "stop" else WARN if rep["level"] == "warn" else OK
    hint = " - writes are REFUSED until the budget allows (newsroom storage status)" if status == FAIL else ""
    return {"object store": _check(status, line + hint, share=max(a["share"], s["share"]))}


def check_db_budget(env: dict[str, str], probes: Probes) -> dict[str, Any]:
    """The free plan's 500 MB database quota (docs/architecture/database-budget.md): warn at 70%, fail at 85%.
    Skipped when the database itself is not reachable (``check_database`` already said so)."""
    if not env.get("DATABASE_URL"):
        return {}
    from algent_backend.database import size

    try:
        rep = probes.db_budget()
    except Exception as exc:  # noqa: BLE001
        return {"database budget": _check(WARN, f"unknown: {scrub(exc, env)}")}
    verdict = size.judge(rep["size_bytes"], rep.get("quota_bytes"))
    hint = "" if verdict["status"] == OK else " - run `newsroom db size`, then `newsroom db prune --apply` (docs/architecture/database-budget.md)"
    out = {"database budget": _check(verdict["status"], size.summary_line({**rep, **verdict}) + hint, share=verdict["share"])}
    if (st := rep.get("storage")):
        top = ", ".join(f"{k}/ {size.human(v)}" for k, v in list(st["by_prefix"].items())[:3])
        out["storage budget"] = _check(st["status"], f"{size.human(st['size_bytes'])} of {size.human(st['quota_bytes'])} ({st['share'] * 100:.0f}%) in published-assets: {top}",
                                       share=st["share"])
    return out


def check_search(env: dict[str, str], probes: Probes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base = (env.get("ALGENT_SEARXNG_URL") or "http://127.0.0.1:8080").rstrip("/")
    try:
        payload = probes.http_get_json(f"{base}/search?q=ohmega&format=json")
        n = len(payload.get("results") or [])
        out["searxng"] = _check(OK if n else WARN, f"answers ({n} results)" if n else "reachable but no results")
    except Exception as exc:  # noqa: BLE001
        out["searxng"] = _check(WARN, f"not reachable at configured url: {scrub(exc, env)} "
                                      "(search falls to DDG/Bing/Google News, then capped paid)")
    answered = 0
    for name in ("ddg", "bing", "gnews"):
        ok, detail = _cached_engine(name, probes)
        answered += ok
        out[f"engine:{name}"] = _check(OK if ok else WARN, detail)
    if out["searxng"]["status"] != OK and not answered:
        out["search:summary"] = _check(FAIL, "no free search path answers; only capped paid engines remain")
    return out


def check_reads(probes: Probes) -> dict[str, Any]:
    out = {"read:playwright": _check(OK, "importable") if probes.playwright_importable()
           else _check(WARN, "not importable (JS-rendered pages unreadable; see requirements)")}
    try:
        res = probes.free_read()
        good = res.get("quality") == "good"
        out["read:free page"] = _check(OK if good else WARN,
                                       f"via {res.get('via')}, quality {res.get('quality')}")
    except Exception as exc:  # noqa: BLE001
        out["read:free page"] = _check(WARN, f"failed: {scrub(exc)}")
    return out


def check_harnesses(probes: Probes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    codex = probes.which("codex")
    if not codex:
        out["harness:codex"] = _check(WARN, "not installed")
    else:
        try:
            rc, text = probes.run([codex, "login", "status"])
            out["harness:codex"] = _check(OK if rc == 0 else WARN,
                                          "logged in" if rc == 0 else f"not logged in: {scrub(text)}")
        except Exception as exc:  # noqa: BLE001
            out["harness:codex"] = _check(WARN, f"status check failed: {scrub(exc)}")
    grok = probes.which("grok") or probes.which(str(Path.home() / ".grok" / "bin" / "grok"))
    if not grok:
        out["harness:grok"] = _check(WARN, "not installed")
    else:
        try:
            rc, text = probes.run([grok, "--version"])
            out["harness:grok"] = _check(OK if rc == 0 else WARN,
                                         f"present ({scrub(text)}); login not verifiable without a prompt call"
                                         if rc == 0 else f"present but --version failed: {scrub(text)}")
        except Exception as exc:  # noqa: BLE001
            out["harness:grok"] = _check(WARN, f"version check failed: {scrub(exc)}")
    return out


def check_publish(env: dict[str, str], probes: Probes, repo: Path) -> dict[str, Any]:
    from algent_backend.publishing import site_git

    db_mode = site_git.via_db()   # SITE_PUBLISH_VIA (flags.py), not merely "a database is configured"
    if db_mode:
        return {"publish": _check(OK, "db mode (publishes rows to the database; connectivity checked above)")}
    try:
        rc, text = probes.run(["git", "ls-remote", "--heads", "origin", "site-live"], timeout=30, cwd=repo)
    except Exception as exc:  # noqa: BLE001
        return {"publish": _check(WARN, f"git unavailable: {scrub(exc)}")}
    if rc != 0:
        return {"publish": _check(FAIL, f"cannot reach origin: {scrub(text)}")}
    if "site-live" not in text:
        return {"publish": _check(WARN, "origin has no site-live branch (read access ok)")}
    return {"publish": _check(OK, "git mode: origin site-live reachable (read access; write is proven at first push)")}


def check_system(probes: Probes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    gb = probes.disk_free_gb()
    out["disk"] = _check(FAIL if gb < _MIN_DISK_GB[0] else WARN if gb < _MIN_DISK_GB[1] else OK, f"{gb:.1f} GB free")
    mb = probes.mem_available_mb()
    out["memory"] = (_check(WARN, "unknown") if mb is None
                     else _check(WARN if mb < _MIN_MEM_MB else OK, f"{mb:.0f} MB available"))
    return out


def check_runner(probes: Probes) -> dict[str, Any]:
    try:
        s = probes.runner_status()
    except Exception as exc:  # noqa: BLE001
        return {"runner": _check(WARN, f"unknown: {scrub(exc)}")}
    if not s.get("reachable"):
        return {"runner": _check(WARN, f"archive unreachable ({scrub(s.get('note', ''))}); guard fails open")}
    if not s.get("runner"):
        return {"runner": _check(WARN, "nobody holds the runner claim (`newsroom runner claim` before paid work)")}
    if s.get("is_runner"):
        return {"runner": _check(OK, f"this machine ({s['this_host']}) is the runner", since=s.get("since"))}
    return {"runner": _check(WARN, f"{s['runner']} is the runner; this machine ({s['this_host']}) will refuse "
                                   "paid work and publishing", since=s.get("since"))}


def check_watchdog(probes: Probes) -> dict[str, Any]:
    from algent_backend.ops import flags

    try:
        age = probes.watchdog_age_minutes()
    except Exception as exc:  # noqa: BLE001
        return {"watchdog": _check(WARN, f"unknown: {scrub(exc)}")}
    if age is None:
        return {"watchdog": _check(WARN, "no pass logged (install the ohmega-watchdog timer: "
                                         "infra/server/install_schedules.sh)")}
    if age > flags.DOCTOR_STALE_MINUTES:
        return {"watchdog": _check(WARN, f"last pass {age:.0f} min ago; is the ohmega-watchdog timer running?")}
    return {"watchdog": _check(OK, f"last pass {age:.0f} min ago")}


def check_schedule(probes: Probes) -> dict[str, Any]:
    """The unattended paid jobs: is each timer installed, is the kill switch on, and how did the last run end?
    A machine without systemd (the laptop) is fine: the timers belong to the server."""
    out: dict[str, Any] = {}
    try:
        enabled, table = probes.scheduled_enabled(), probes.scheduled_jobs()
    except Exception as exc:  # noqa: BLE001
        return {"schedule": _check(WARN, f"unknown: {scrub(exc)}")}
    if not enabled:
        out["schedule"] = _check(WARN, "scheduled paid runs are PAUSED (SCHEDULED_PAID_RUNS is off in ops/flags.py)")
    for job, info in table.items():
        try:
            state = probes.timer_state(job)
        except Exception as exc:  # noqa: BLE001
            state = f"unknown ({scrub(exc)})"
        last = info.get("last")
        said = (f"last: {last['outcome']} {last['ts']}" + (f" (${last['usd']:.2f})" if last.get("usd") is not None else "")
                + (f", {last['why']}" if last.get("why") else "")) if last else "no run recorded yet"
        if state is None:
            out[f"schedule:{job}"] = _check(OK, f"{info['utc']} UTC; no systemd on this machine; {said}")
        elif state != "enabled":
            out[f"schedule:{job}"] = _check(WARN, f"{info['utc']} UTC; timer is {state} (infra/server/install_schedules.sh); {said}")
        else:
            out[f"schedule:{job}"] = _check(WARN if last and last["outcome"] == "failed" else OK,
                                            f"{info['utc']} UTC; timer enabled; {said}")
    return out


def check_quota(probes: Probes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for provider, row in probes.quota_summary().items():
        used, cap = row["used"], row["cap"]
        status = OK if used < 0.8 * cap else WARN
        out[f"quota:{provider}"] = _check(status, f"{used}/{cap} this month")
    return out


def check_instruments() -> dict[str, Any]:
    """Numbers-layer feeds judged against their own release cadence: a series with nothing stored or whose newest
    reading is older than its cadence + lag allows is a broken feed (a weekly feed a week old is fine)."""
    try:
        from datetime import date

        from algent_backend.instruments import freshness, store
        from algent_backend.instruments.catalog import CATALOG

        if not store.stored_ids():
            return {"instruments": _check(OK, "no instrument store on this machine (numbers layer not collected here)")}
        bad = []
        for s in CATALOG:
            if s.fetcher == "live":              # judged by check_live (a keyed feed without its key is not "overdue")
                continue
            hist = store.history(s.id)
            if not hist:
                bad.append(f"{s.id} (nothing stored)")
            elif (f := freshness.assess(s, hist[-1].period, date.today()))["status"] == "overdue":
                bad.append(f"{s.id} ({f['note']})")
    except Exception as exc:  # noqa: BLE001 - a readiness aid must not crash the doctor
        return {"instruments": _check(WARN, f"unknown: {scrub(exc)}")}
    return {"instruments": _check(WARN, f"{len(bad)} overdue/empty feeds: {'; '.join(bad)}") if bad
            else _check(OK, "every feed is as fresh as its cadence allows")}


def check_live(env: dict[str, str]) -> dict[str, Any]:
    """Live feeds (free collectors): last successful fetch per feed, and which keyed feeds lack their free key.
    A keyless feed that never succeeded or is long silent is a warning; a missing key is reported with its signup."""
    try:
        from datetime import datetime, timezone

        from algent_backend.live import flags as live_flags
        from algent_backend.live import runner
    except Exception as exc:  # noqa: BLE001
        return {"live": _check(WARN, f"unknown: {scrub(exc)}")}
    out: dict[str, Any] = {}
    now = datetime.now(timezone.utc)
    for row in runner.doctor_rows():
        name = f"live:{row['feed']}"
        if row["needs"]:
            out[name] = _check(WARN, row["needs"])
            continue
        if not row["last_ok"]:
            out[name] = _check(WARN, "never succeeded on this machine" + (f" ({scrub(row['error'], env)})" if row["error"] else ""))
            continue
        age = (now - datetime.fromisoformat(row["last_ok"])).total_seconds() / 60
        # silent = several of the feed's own cadences missed (the AIS service flushes every few minutes)
        every = live_flags.CADENCE_MINUTES.get(row["feed"], live_flags.AIS_FLUSH_SECONDS / 60)
        out[name] = _check(WARN if age > 4 * every + 5 else OK,
                           f"last ok {age:.0f} min ago" + (f"; {scrub(row['error'], env)}" if row["error"] else ""))
    return out


def check_sanctions() -> dict[str, Any]:
    """Sanctions list feeds: every source fetched well within ``flags.STALE_HOURS``. Nothing on this machine is fine (not collected here)."""
    try:
        from datetime import datetime, timezone

        from algent_backend.sanctions import flags, store

        status = store.load_status()
        if not status:
            return {"sanctions": _check(OK, "no sanctions store on this machine (feed not collected here)")}
        now, bad = datetime.now(timezone.utc), []
        for src in ("ofac", "uk", "eu"):
            row = status.get(src) or {}
            if not row.get("last_ok"):
                bad.append(f"{src} (never fetched" + (f": {scrub(row.get('last_error', ''))}" if row.get("last_error") else "") + ")")
            elif (now - datetime.fromisoformat(row["last_ok"])).total_seconds() > flags.STALE_HOURS * 3600:
                bad.append(f"{src} (last ok {row['last_ok'][:16]}Z)")
    except Exception as exc:  # noqa: BLE001
        return {"sanctions": _check(WARN, f"unknown: {scrub(exc)}")}
    return {"sanctions": _check(WARN, "stale: " + "; ".join(bad)) if bad else _check(OK, "all three lists fetched recently")}


def check_maritime() -> dict[str, Any]:
    """Maritime behaviour memory: the stream service cycled recently (state.json) and the profile book exists. Nothing here is fine (the stream runs elsewhere)."""
    try:
        import time

        from algent_backend.maritime import store

        state = store.read_state()
        if not state:
            return {"maritime": _check(OK, "no maritime store on this machine (the stream service runs elsewhere)")}
        age = (time.time() - float(state.get("last_cycle", 0.0))) / 60
        if age > 30:
            return {"maritime": _check(WARN, f"behaviour memory last cycled {age:.0f} min ago (is ohmega-ais running?)")}
        events = len(store.read_current())
    except Exception as exc:  # noqa: BLE001
        return {"maritime": _check(WARN, f"unknown: {scrub(exc)}")}
    return {"maritime": _check(OK, f"cycled {age:.0f} min ago; {events} events in the picture")}


def check_calendar() -> dict[str, Any]:
    """Calendar sources: each fetched within a day and a half. Sources are best-effort pages, so a stale one is a warning."""
    try:
        from datetime import date, datetime, timezone

        from algent_backend.lookahead import store

        status = store.load_status()
        if not status:
            return {"calendar": _check(OK, "no calendar store on this machine (not collected here)")}
        now, bad = datetime.now(timezone.utc), []
        for src in ("fed", "ecb", "boe", "elections", "unsc", "opec"):
            row = status.get(src) or {}
            if not row.get("last_ok"):
                bad.append(f"{src} (never ok" + (f": {scrub(row.get('last_error', ''))}" if row.get("last_error") else "") + ")")
            elif (now - datetime.fromisoformat(row["last_ok"])).total_seconds() > 36 * 3600:
                bad.append(f"{src} (last ok {row['last_ok'][:16]}Z)")
        n = len(store.upcoming(date.today(), 30))
    except Exception as exc:  # noqa: BLE001
        return {"calendar": _check(WARN, f"unknown: {scrub(exc)}")}
    return {"calendar": _check(WARN, "stale: " + "; ".join(bad)) if bad else _check(OK, f"all sources fresh; {n} items in the next 30 days")}


def check_markets() -> dict[str, Any]:
    """The Polymarket mirror: a good pass within 10 hours (the timer fires every 4). Read-only data, so stale is a warning."""
    try:
        from datetime import datetime, timezone

        from algent_backend.markets import store

        st = store.load_status()
        if not st:
            return {"markets": _check(OK, "no markets store on this machine (not collected here)")}
        if not st.get("last_ok"):
            return {"markets": _check(WARN, "never ok" + (f": {scrub(st.get('last_error', ''))}" if st.get("last_error") else ""))}
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(st["last_ok"])).total_seconds() / 3600
        ms = store.markets().values()
        n = sum(1 for m in ms if m.status == "open")
    except Exception as exc:  # noqa: BLE001
        return {"markets": _check(WARN, f"unknown: {scrub(exc)}")}
    if age > 10:
        return {"markets": _check(WARN, f"stale: last good pass {age:.0f} h ago")}
    return {"markets": _check(OK, f"mirrored {age:.1f} h ago; {n} open markets, {len(store.forecasts())} forecasts (paper only)")}


def check_ai_benchmarks() -> dict[str, Any]:
    """The AI benchmark tracker: every free source fetched recently, parsing, and still publishing new results (``ai_benchmarks/freshness``).
    Stale or broken sources are warnings, named with the reason. Nothing on this machine is fine (not collected here)."""
    try:
        from algent_backend.ai_benchmarks import freshness, store

        if not store.load_status():
            return {"ai_benchmarks": _check(OK, "no AI benchmark store on this machine (not collected here)")}
        rows = freshness.source_health()
        bad = [f"{r['source']} ({'; '.join(r['reasons'])})" for r in rows if r["stale"]]
        n = len(store.current())
    except Exception as exc:  # noqa: BLE001
        return {"ai_benchmarks": _check(WARN, f"unknown: {scrub(exc)}")}
    return {"ai_benchmarks": _check(WARN, "stale: " + scrub("; ".join(bad))) if bad else _check(OK, f"{len(rows)} sources fresh; {n} scores stored")}


def check_satellite() -> dict[str, Any]:
    """Satellite watch: the last pass is within two days (the timer runs daily). Nothing on this machine is fine (not collected here)."""
    try:
        import time
        from datetime import datetime

        from algent_backend.satellite import store

        doc = store.read_json("doc.json")
        if not doc:
            return {"satellite": _check(OK, "no satellite store on this machine (collected on the server)")}
        age_h = (time.time() - datetime.fromisoformat(doc["as_of"]).timestamp()) / 3600
        counts = doc.get("counts") or {}
    except Exception as exc:  # noqa: BLE001
        return {"satellite": _check(WARN, f"unknown: {scrub(exc)}")}
    if age_h > 48:
        return {"satellite": _check(WARN, f"last pass {age_h:.0f} h ago (is ohmega-satellite running?)")}
    return {"satellite": _check(OK, f"last pass {age_h:.0f} h ago; {counts.get('with_imagery', 0)} of {counts.get('watched', 0)} sites have imagery")}


def check_basemap(probes: Probes) -> dict[str, Any]:
    """The Natural Earth basemap (untracked data) must load, or every daily map silently disappears."""
    try:
        loaded = probes.basemap_loaded()
    except Exception as exc:  # noqa: BLE001
        return {"basemap": _check(WARN, f"unknown: {scrub(exc)}")}
    return {"basemap": _check(OK, "Natural Earth countries load") if loaded else _check(
        WARN, "Natural Earth basemap missing: daily maps and places will be empty. Copy "
              "analytics_workspace/data/natural_earth/ from a machine that has it (docs/guides/worker-server.md)")}


def run_checks(env: dict[str, str] | None = None, probes: Probes | None = None,
               repo: Path | None = None) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    probes = probes or Probes()
    repo = repo or Path(__file__).resolve().parents[3]
    checks: dict[str, Any] = {}
    for part in (check_keys(env), check_database(env, probes), check_object_store(env), check_search(env, probes), check_reads(probes),
                 check_harnesses(probes), check_publish(env, probes, repo), check_runner(probes),
                 check_system(probes), check_watchdog(probes), check_schedule(probes), check_quota(probes), check_instruments(), check_live(env), check_sanctions(), check_maritime(), check_calendar(), check_markets(), check_ai_benchmarks(), check_satellite(), check_basemap(probes)):
        checks.update(part)
    if checks.get("database", {}).get("status") == OK:        # the size check needs a reachable database
        checks.update(check_db_budget(env, probes))
    counts = {s: sum(1 for c in checks.values() if c["status"] == s) for s in (OK, WARN, FAIL)}
    return {"ok": counts[FAIL] == 0, "summary": f"{counts[OK]} ok, {counts[WARN]} warn, {counts[FAIL]} fail",
            "checks": checks}
