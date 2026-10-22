"""
Object-store usage guard - the R2 free tier as a hard budget (docs/architecture/database-budget.md, "R2 budget").

R2 has a card on file, so an overage bills. Every call ``R2Store`` makes goes through a ``Meter`` that keeps, in a small local file
(``publish_held/r2_usage.json``), this month's count of

* Class A operations (PUT / LIST / DELETE; the free tier is 1 M a month),
* Class B operations (GET / HEAD; 10 M a month),
* bytes stored (the size of every object we last wrote, summed; the free tier is 10 GB-month).

``check`` is called BEFORE a call: past ``R2_STOP_SHARE`` (90%) of the monthly free quantity, or past ``R2_DAILY_STOP_MULT`` times the day's
even share, it returns a reason and the store refuses (HTTP 429 to the uploader, which reports a failed object and moves on; the live
publishers skip the cycle, nothing raises). ``status`` is what ``newsroom storage status`` and ``newsroom doctor`` print.

The file is shared by the timer processes and the always-on stream service: each process counts in memory and merges its delta into the
file on ``flush`` (at most every 2 s and at the end of every upload batch), so two processes add rather than overwrite. The meter counts
what the SERVER does; the site's public reads are Class B too and are visible only in the Cloudflare dashboard (the doc budgets them).
"""

from __future__ import annotations

import calendar
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from algent_backend.database import flags

CLASS_A, CLASS_B = "a", "b"
_FLUSH_EVERY_S = 2.0
_LOG_EVERY_S = 60.0
_CACHE_S = 5.0


def _fresh(month: str) -> dict[str, Any]:
    return {"month": month, "a": 0, "b": 0, "days": {}, "objects": {}}


class Meter:
    def __init__(self, path: Path, *, now: Callable[[], datetime] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = Path(path)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._clock = clock
        self._lock = threading.RLock()
        self._delta: dict[str, Any] = {"a": 0, "b": 0, "days": {}, "objects": {}}
        self._last_flush = 0.0
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._last_log = -1e9
        self.last_refusal = ""

    # ── persistence ──────────────────────────────────────────────────────────────────────────────
    def _month(self) -> str:
        return self._now().strftime("%Y-%m")

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        month = self._month()
        if not isinstance(data, dict) or data.get("month") != month:
            fresh = _fresh(month)
            if isinstance(data, dict):
                fresh["objects"] = data.get("objects", {}) if isinstance(data.get("objects"), dict) else {}   # storage is a stock, not a flow
            return fresh
        for k, default in _fresh(month).items():
            data.setdefault(k, default)
        return data

    def _base(self) -> dict[str, Any]:
        """The file's content, re-read at most every few seconds (a publish batch makes hundreds of checks)."""
        if self._cache is not None and self._clock() - self._cache[0] < _CACHE_S and self._cache[1].get("month") == self._month():
            return self._cache[1]
        data = self._read()
        self._cache = (self._clock(), data)
        return data

    def _merged(self, base: dict[str, Any]) -> dict[str, Any]:
        out = {**base, "a": base["a"] + self._delta["a"], "b": base["b"] + self._delta["b"],
               "days": {k: list(v) for k, v in base["days"].items()}, "objects": dict(base["objects"])}
        for day, (a, b) in self._delta["days"].items():
            cur = out["days"].setdefault(day, [0, 0])
            out["days"][day] = [cur[0] + a, cur[1] + b]
        for key, size in self._delta["objects"].items():
            if size is None:
                out["objects"].pop(key, None)
            else:
                out["objects"][key] = size
        return out

    def flush(self) -> None:
        with self._lock:
            if not (self._delta["a"] or self._delta["b"] or self._delta["objects"]):
                return
            self._cache = None
            merged = self._merged(self._read())
            merged["days"] = dict(sorted(merged["days"].items())[-40:])
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(merged, separators=(",", ":")), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError:
                return                       # keep the delta; the next flush retries
            self._delta = {"a": 0, "b": 0, "days": {}, "objects": {}}
            self._last_flush = self._clock()

    def usage(self) -> dict[str, Any]:
        with self._lock:
            u = self._merged(self._base())
        u["bytes"] = sum(int(v) for v in u["objects"].values())
        return u

    # ── the guard ────────────────────────────────────────────────────────────────────────────────
    def check(self, cls: str, add_bytes: int = 0, key: str | None = None) -> str:
        """Why this call must not be made ("" = go ahead)."""
        u = self.usage()
        now = self._now()
        days = calendar.monthrange(now.year, now.month)[1]
        free = flags.R2_FREE_CLASS_A if cls == CLASS_A else flags.R2_FREE_CLASS_B
        label = "Class A" if cls == CLASS_A else "Class B"
        if u[cls] >= flags.R2_STOP_SHARE * free:
            return f"R2 {label} operations at {u[cls]:,} of the {free:,} monthly free tier (hard stop at {flags.R2_STOP_SHARE:.0%})"
        today = u["days"].get(now.strftime("%Y-%m-%d"), [0, 0])[0 if cls == CLASS_A else 1]
        cap = flags.R2_DAILY_STOP_MULT * free / days
        if today >= cap:
            return f"R2 {label} operations today {today:,} reached the daily cap {int(cap):,} ({flags.R2_DAILY_STOP_MULT:g}x the even daily share)"
        if cls == CLASS_A and add_bytes:
            previous = int(u["objects"].get(key, 0)) if key else 0
            if u["bytes"] - previous + add_bytes >= flags.R2_STOP_SHARE * flags.R2_FREE_STORAGE_BYTES:
                return f"R2 storage would reach {u['bytes'] + add_bytes:,} of the {flags.R2_FREE_STORAGE_BYTES:,} byte free tier (hard stop at {flags.R2_STOP_SHARE:.0%})"
        return ""

    def refuse(self, reason: str) -> None:
        """Log a refusal (once a minute at most) and remember it for the status line."""
        self.last_refusal = reason
        if self._clock() - self._last_log >= _LOG_EVERY_S:
            self._last_log = self._clock()
            print(f"[object_store] REFUSED {reason}; the cycle is skipped and retried when the budget allows", flush=True)

    def record(self, cls: str, *, key: str | None = None, size: int | None = None, removed: bool = False) -> None:
        with self._lock:
            self._delta[cls] += 1
            day = self._now().strftime("%Y-%m-%d")
            cur = self._delta["days"].setdefault(day, [0, 0])
            cur[0 if cls == CLASS_A else 1] += 1
            if key is not None and (removed or size is not None):
                self._delta["objects"][key] = None if removed else int(size or 0)
            if self._clock() - self._last_flush >= _FLUSH_EVERY_S:
                self.flush()

    # ── the report ───────────────────────────────────────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        u = self.usage()
        now = self._now()
        days = calendar.monthrange(now.year, now.month)[1]
        elapsed = now.day - 1 + (now.hour + now.minute / 60) / 24 or 1 / 24
        today_a, today_b = u["days"].get(now.strftime("%Y-%m-%d"), [0, 0])
        rows = {}
        for name, used, free, today in (("class_a", u["a"], flags.R2_FREE_CLASS_A, today_a), ("class_b", u["b"], flags.R2_FREE_CLASS_B, today_b),
                                        ("storage_bytes", u["bytes"], flags.R2_FREE_STORAGE_BYTES, None)):
            share = used / free
            projected = used if name == "storage_bytes" else used / elapsed * days
            rows[name] = {"used": used, "free_tier": free, "share": round(share, 4), "daily_allowance": None if today is None else int(free / days),
                          "today": today, "projected_month": int(projected), "projected_share": round(projected / free, 4),
                          "level": "stop" if share >= flags.R2_STOP_SHARE else "warn" if share >= flags.R2_WARN_SHARE else "ok"}
        level = "stop" if any(r["level"] == "stop" for r in rows.values()) else "warn" if any(r["level"] == "warn" for r in rows.values()) else "ok"
        if level != "stop" and (self.check(CLASS_A) or self.check(CLASS_B)):          # a daily cap can stop writes before the month does
            level = "stop"
        return {"month": u["month"], "level": level, "objects": len(u["objects"]), "usage": rows, "last_refusal": self.last_refusal,
                "note": "counts this server's calls only; the site's public reads are Class B too - see the Cloudflare dashboard"}


_METERS: dict[str, Meter] = {}


def meter(path: Path | None = None) -> Meter:
    """The process-wide meter for the usage file (one per path, so tests with their own ``ALGENT_PUBLISH_HELD`` stay separate)."""
    from .object_store import held_dir

    p = Path(path) if path else held_dir() / "r2_usage.json"
    key = str(p)
    if key not in _METERS:
        _METERS[key] = Meter(p)
    return _METERS[key]
