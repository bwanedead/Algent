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
    ("database", ("DATABASE_URL",), FAIL),
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

    def runner_status(self) -> dict[str, Any]:
        from algent_backend.data_backup import runner

        return runner.status()

    def quota_summary(self) -> dict[str, dict[str, int]]:
        from algent_backend.agent_system.tools.sourcing.search import quota

        return quota.summary()

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
    if not env.get("DATABASE_URL"):
        return {"database": _check(FAIL, "DATABASE_URL not set")}
    try:
        probes.db_select1()
    except Exception as exc:  # noqa: BLE001
        return {"database": _check(FAIL, f"not reachable: {scrub(exc, env)}")}
    return {"database": _check(OK, "connected, select 1 ok")}


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
    db_mode = bool(env.get("DATABASE_URL")) and env.get("ALGENT_DB_PUBLISH", "1").strip().lower() not in (
        "0", "false", "no", "off")
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


def check_quota(probes: Probes) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for provider, row in probes.quota_summary().items():
        used, cap = row["used"], row["cap"]
        status = OK if used < 0.8 * cap else WARN
        out[f"quota:{provider}"] = _check(status, f"{used}/{cap} this month")
    return out


def run_checks(env: dict[str, str] | None = None, probes: Probes | None = None,
               repo: Path | None = None) -> dict[str, Any]:
    env = dict(os.environ if env is None else env)
    probes = probes or Probes()
    repo = repo or Path(__file__).resolve().parents[3]
    checks: dict[str, Any] = {}
    for part in (check_keys(env), check_database(env, probes), check_search(env, probes), check_reads(probes),
                 check_harnesses(probes), check_publish(env, probes, repo), check_runner(probes),
                 check_system(probes), check_quota(probes)):
        checks.update(part)
    counts = {s: sum(1 for c in checks.values() if c["status"] == s) for s in (OK, WARN, FAIL)}
    return {"ok": counts[FAIL] == 0, "summary": f"{counts[OK]} ok, {counts[WARN]} warn, {counts[FAIL]} fail",
            "checks": checks}
