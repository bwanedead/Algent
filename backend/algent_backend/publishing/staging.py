"""
The staging channel: publish the SAME documents to ``<bucket>/staging/…`` so a preview deployment can read them and production never does
(docs/guides/deploy.md). A schema change is published to staging, checked on the preview site, then promoted by publishing to production as usual.

How it is wired (the publishers know nothing about it):

* ``target()`` is ``ALGENT_PUBLISH_TARGET`` (``production`` by default, ``staging``). The CLI's ``--target staging`` sets it for the process.
* ``object_store.select()`` wraps the real store in a ``StagingStore`` when the target is staging. Every publisher already gets its store from
  ``select()``, so every one of them - documents, views, live snapshots, images - lands under the prefix with no change of its own.
* The wrapper's ``ident`` differs (``r2:<bucket>:staging``), so the local hash manifests keep staging and production apart: staging is hash-skipped
  by itself and production's "already sent" never hides a document staging has not got.
* The wrapped store still goes through the shared R2 meter (the free-tier guard sees staging), and ``Ledger`` adds a much lower allowance of its own:
  ``STAGING_CLASS_A_PER_DAY`` operations a day and ``STAGING_MAX_BYTES`` held. Past either the put is refused (HTTP 429, the uploader reports a failed
  object and retries next run), exactly like the production guard.
* Retention: the ledger records when each staged key was last written. ``prune()`` (``newsroom publish staging-prune``, the daily ``staging-prune`` job)
  deletes keys older than ``STAGING_KEEP_DAYS`` and forgets their hashes. An R2 lifecycle rule on the prefix is the second line (the deploy guide).

The ledger is server-local state in ``publish_held/staging_ledger.json`` (never read back from the bucket, like every other manifest).
"""

from __future__ import annotations

import atexit
import json
import os
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.database import flags

ENV = "ALGENT_PUBLISH_TARGET"
PRODUCTION, STAGING = "production", "staging"
TARGETS = (PRODUCTION, STAGING)
_FLUSH_EVERY_S = 2.0
_LOG_EVERY_S = 60.0


def target(env: Mapping[str, str] | None = None) -> str:
    """The publish target of this process: ``production`` unless ``ALGENT_PUBLISH_TARGET`` says otherwise (any value that is not a target is returned
    as is, and ``object_store.select`` then refuses to publish at all rather than guess)."""
    env = os.environ if env is None else env
    return env.get(ENV, "").strip().lower() or PRODUCTION


def is_staging(env: Mapping[str, str] | None = None) -> bool:
    return target(env) == STAGING


def set_target(name: str | None) -> None:
    """Make this process publish to ``name`` (the CLI's ``--target``). None or ``production`` clears it."""
    if not name or name == PRODUCTION:
        os.environ.pop(ENV, None)
    else:
        os.environ[ENV] = name


@contextmanager
def using(name: str) -> Iterator[None]:
    """Publish to ``name`` for the duration of the block, then put the previous target back."""
    before = os.environ.get(ENV)
    set_target(name)
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = before


def prefix() -> str:
    return flags.STAGING_PREFIX.strip("/") + "/"


def key_of(production_key: str) -> str:
    """The bucket key staging uses for a production key (``docs/x.gz`` -> ``staging/docs/x.gz``)."""
    return prefix() + production_key.lstrip("/")


# ── the ledger: what staging holds, and its own allowance ─────────────────────────────────────────────────────────�
class Ledger:
    """Server-local record of the staged objects (key -> [last written, bytes]) and of today's Class A operations."""

    def __init__(self, path: Path, *, now: Callable[[], datetime] | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = Path(path)
        self._now = now or (lambda: datetime.now(UTC))
        self._clock = clock
        self._lock = threading.RLock()
        self._state = self._read()
        self._dirty = False
        self._last_flush = 0.0
        self._last_log = -1e9
        self.last_refusal = ""

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault("objects", {})
        data.setdefault("days", {})
        return data

    def flush(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                self._state["days"] = dict(sorted(self._state["days"].items())[-40:])
                tmp.write_text(json.dumps(self._state, separators=(",", ":"), sort_keys=True), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError:
                return
            self._dirty = False
            self._last_flush = self._clock()

    def _touch(self) -> None:
        self._dirty = True
        if self._clock() - self._last_flush >= _FLUSH_EVERY_S:
            self.flush()

    def bytes_held(self) -> int:
        return sum(int(v[1]) for v in self._state["objects"].values())

    def today(self) -> int:
        return int(self._state["days"].get(self._now().strftime("%Y-%m-%d"), 0))

    def reserve(self, key: str, size: int) -> str:
        """Check the staging allowance for one PUT of ``size`` bytes and count the operation. Returns the refusal reason, or "" to go ahead."""
        with self._lock:
            if self.today() >= flags.STAGING_CLASS_A_PER_DAY:
                return f"staging used its {flags.STAGING_CLASS_A_PER_DAY:,} operations for today (database/flags.py STAGING_CLASS_A_PER_DAY)"
            previous = int(self._state["objects"].get(key, [0, 0])[1])
            if self.bytes_held() - previous + size > flags.STAGING_MAX_BYTES:
                return f"staging would hold more than {flags.STAGING_MAX_BYTES:,} bytes (STAGING_MAX_BYTES); run staging-prune or raise the allowance"
            self._count()
            return ""

    def _count(self) -> None:
        day = self._now().strftime("%Y-%m-%d")
        self._state["days"][day] = int(self._state["days"].get(day, 0)) + 1
        self._touch()

    def refuse(self, reason: str) -> None:
        self.last_refusal = reason
        if self._clock() - self._last_log >= _LOG_EVERY_S:
            self._last_log = self._clock()
            print(f"[staging] REFUSED {reason}; the object is retried on the next run", flush=True)

    def wrote(self, key: str, size: int) -> None:
        with self._lock:
            self._state["objects"][key] = [self._now().isoformat(timespec="seconds"), int(size)]
            self._touch()

    def removed(self, key: str, *, count: bool = True) -> None:
        with self._lock:
            self._state["objects"].pop(key, None)
            if count:
                self._count()
            else:
                self._touch()

    def stale(self, days: float | None = None) -> list[str]:
        """Keys last written more than ``days`` (default ``STAGING_KEEP_DAYS``) ago."""
        cut = (self._now() - timedelta(days=flags.STAGING_KEEP_DAYS if days is None else days)).isoformat(timespec="seconds")
        with self._lock:
            return sorted(k for k, v in self._state["objects"].items() if str(v[0]) < cut)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"objects": len(self._state["objects"]), "bytes": self.bytes_held(), "bytes_cap": flags.STAGING_MAX_BYTES,
                    "class_a_today": self.today(), "class_a_per_day": flags.STAGING_CLASS_A_PER_DAY, "keep_days": flags.STAGING_KEEP_DAYS,
                    "last_refusal": self.last_refusal}


_LEDGERS: dict[str, Ledger] = {}


def ledger(path: Path | None = None) -> Ledger:
    """The process-wide ledger for the file (one per path, so tests with their own ``ALGENT_PUBLISH_HELD`` stay apart)."""
    from .object_store import held_dir

    p = Path(path) if path else held_dir() / "staging_ledger.json"
    if str(p) not in _LEDGERS:
        _LEDGERS[str(p)] = Ledger(p)
        atexit.register(_LEDGERS[str(p)].flush)
    return _LEDGERS[str(p)]


# ── the store ───────────────────────────────────────────────────────────────────────────────�
class _Flush:
    """What ``asset_store`` calls at the end of a batch: persist the shared R2 meter and the staging ledger together."""

    def __init__(self, inner_meter: Any, led: Ledger) -> None:
        self._inner, self._led = inner_meter, led

    def flush(self) -> None:
        if self._inner is not None:
            self._inner.flush()
        self._led.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class StagingStore:
    """An object store whose every key lives under ``staging/``. Same interface as ``object_store.ObjectStore``."""

    def __init__(self, inner: Any, led: Ledger | None = None) -> None:
        self.inner = inner
        self.name = inner.name
        self.ident = f"{inner.ident}:{flags.STAGING_PREFIX}"
        self.ledger = led or ledger()

    def put(self, key: str, data: bytes, *, content_type: str, cache_control: str, content_encoding: str | None = None) -> int:
        k = key_of(key)
        if (why := self.ledger.reserve(k, len(data))):
            self.ledger.refuse(why)
            return 429
        status = self.inner.put(k, data, content_type=content_type, cache_control=cache_control, content_encoding=content_encoding)
        if 200 <= status < 300:
            self.ledger.wrote(k, len(data))
        return status

    def get(self, key: str) -> bytes | None:
        return self.inner.get(key_of(key))

    def head(self, key: str) -> dict[str, str] | None:
        return self.inner.head(key_of(key))

    def delete(self, key: str) -> bool:
        ok = self.inner.delete(key_of(key))
        if ok:
            self.ledger.removed(key_of(key))
        return ok

    def list(self, prefix_: str = "") -> list[dict[str, Any]]:
        rows = self.inner.list(key_of(prefix_))
        return [{**r, "key": r["key"][len(prefix()):]} for r in rows]

    def public_url(self, key: str) -> str:
        return self.inner.public_url(key_of(key))

    def meter(self) -> _Flush:
        return _Flush(self.inner.meter() if hasattr(self.inner, "meter") else None, self.ledger)


# ── retention ───────────────────────────────────────────────────────────────────────────────�
def _forget_hashes(ident: str, keys: list[str]) -> None:
    """Drop the staging hash-manifest entries of pruned keys, so a later stage-from-prod re-sends them instead of believing they are still there."""
    from . import asset_store, object_docs

    gone = set(keys)
    for path, doc_for in ((object_docs.manifest_path(), True), (asset_store._manifest_path(), False)):  # noqa: SLF001 - same package
        state = object_docs._load(path)  # noqa: SLF001
        drop = []
        for mk in state:
            if not mk.startswith(ident + "|"):
                continue
            rel = mk.split("|", 1)[1]
            bucket_key = key_of(f"docs/{rel}.gz" if doc_for else rel)
            if bucket_key in gone:
                drop.append(mk)
        if drop:
            for mk in drop:
                state.pop(mk)
            object_docs._save(path, state)  # noqa: SLF001


def prune(store: Any | None = None, *, days: float | None = None, dry_run: bool = False, led: Ledger | None = None) -> dict[str, Any]:
    """Delete staged objects not written for ``days`` (default ``STAGING_KEEP_DAYS``). ``store`` is the REAL store (not the wrapper); None selects the
    configured one for the production target. Reads nothing from the bucket: the ledger says what is there. Never raises."""
    from . import object_store

    led = led or ledger()
    keys = led.stale(days)
    out: dict[str, Any] = {"stale": len(keys), "deleted": 0, "failed": 0, "dry_run": dry_run, "keep_days": flags.STAGING_KEEP_DAYS if days is None else days}
    if dry_run or not keys:
        out["ok"] = True
        out["ledger"] = led.status()
        return out
    try:
        base = store or object_store.select(env={**os.environ, ENV: PRODUCTION})
        if base is None:
            return {**out, "ok": False, "note": "no object store configured (R2_* names)"}
        done = []
        for k in keys:
            if base.delete(k):
                led.removed(k)
                done.append(k)
            else:
                out["failed"] += 1
        out["deleted"] = len(done)
        _forget_hashes(f"{base.ident}:{flags.STAGING_PREFIX}", done)
        if hasattr(base, "meter"):
            base.meter().flush()
        led.flush()
        out["ok"] = out["failed"] == 0
    except Exception as exc:  # noqa: BLE001 - housekeeping must not crash the job runner
        out.update(ok=False, note=f"{type(exc).__name__}: {str(exc)[:160]}")
    out["ledger"] = led.status()
    return out
