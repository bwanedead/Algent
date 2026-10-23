"""
Per-product status files: "is it alive" (``checked_at``) apart from "what's new" (``last_changed_at``) - docs/architecture/foundation.md, "Checked vs changed".

A product whose content did not change (sanctions with no new designation, a calendar with no new event) used to keep an old ``as_of`` and so looked
stale on the site and in the hourly smoke test although its job ran fine. The job runner (``products/run.py``) now ends every run of a publishing product
here:

* **failure**: a local note only (``last_failed_at``); nothing is uploaded, so the published file keeps saying when the product was last checked.
* **success**: ``<held>/status/<product>.json`` (the local copy, the memory for the next run) and the published ``docs/status/<product>.json.gz``, a
  document of schema ``ohmega.status/1``::

      {schema, product, job, checked_at, last_changed_at, last_ok, last_failed_at, next_due, cadence_min}

  ``checked_at`` is the end of the last successful run; ``last_changed_at`` is the newest time a run of this product actually uploaded a new object
  (``publishing/changed.py``; hash-skipped objects do not count); ``next_due`` is ``checked_at`` plus the registry's shortest job interval for it.

Cost: one PUT (Class A) per successful run per product, bounded two ways. A product that runs every hour or slower always writes; a faster one (live feeds,
the 30-minute views build) writes at most once per ``MIN_GAP_MIN``, and an unchanged document is hash-skipped like any other. ``puts_per_day`` computes the
figure from the registry; ``newsroom products status`` prints it next to the guard's allowance.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.publishing import changed

SCHEMA = "ohmega.status/1"
#: A product that runs more often than hourly publishes its status at most this often (minutes). Chosen below the smoke test's lateness bound (twice this).
MIN_GAP_MIN = 30.0
#: Products whose pages are not data the site reads: no status file (staging is a copy of production under another prefix).
EXCLUDED = ("staging",)


def doc_path(product: str) -> str:
    """The document path (``docs/<path>.gz`` in the bucket)."""
    return f"status/{product}.json"


def local_path(product: str) -> Path:
    from algent_backend.publishing import object_store

    return object_store.held_dir() / "status" / f"{product}.json"


def read_local(product: str) -> dict[str, Any]:
    try:
        d = json.loads(local_path(product).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_local(product: str, doc: dict[str, Any]) -> None:
    try:
        p = local_path(product)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def tracked(product: Any) -> bool:
    """A product has a status file when it publishes something and runs on a timer."""
    return bool(product.publishes) and product.id not in EXCLUDED and any(j.kind == "timer" for j in product.job_list())


def cadence_min(product: Any) -> float:
    """The shortest healthy gap between runs of the product's timers (the registry's ``every_min``); 0 when it has none."""
    return min((j.every_min for j in product.job_list() if j.kind == "timer" and j.every_min), default=0.0)


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat(timespec="seconds")


def _due(product: Any, prev: dict[str, Any], t: datetime) -> bool:
    """Whether this success should be uploaded now: always for an hourly-or-slower product, otherwise at most every ``MIN_GAP_MIN``."""
    cad = cadence_min(product)
    if cad == 0 or cad >= 60:
        return True
    try:
        last = datetime.fromisoformat(str(prev.get("published_at")))
    except (TypeError, ValueError):
        return True
    return t - last >= timedelta(minutes=MIN_GAP_MIN)


def record(product: Any, job: str, ok: bool, *, now: datetime | None = None, http: Any = None) -> dict[str, Any] | None:
    """End-of-run bookkeeping for ``job`` of ``product``. Returns the status document (also when it was not uploaded), None for an untracked product.
    Never raises: the status is an addition to the run, not part of it."""
    if not tracked(product):
        return None
    try:
        t = now or datetime.now(UTC)
        prev = read_local(product.id)
        if not ok:
            prev.update(last_failed_at=_iso(t), last_failed_job=job)
            _write_local(product.id, prev)
            return prev
        cad = cadence_min(product)
        newest = changed.last_change(product.id)
        doc = {"schema": SCHEMA, "product": product.id, "job": job, "checked_at": _iso(t), "last_ok": True,
               "last_changed_at": max(str(prev.get("last_changed_at") or ""), newest) or None,
               "last_failed_at": prev.get("last_failed_at"), "cadence_min": cad or None,
               "next_due": _iso(t + timedelta(minutes=cad)) if cad else None}
        upload = _due(product, prev, t)
        local = {**doc, "published_at": prev.get("published_at")}
        if upload:
            from algent_backend.publishing import object_docs

            res = object_docs.publish({doc_path(product.id): doc}, http=http, names=False)
            if res.get("documents"):
                local["published_at"] = _iso(t)
        _write_local(product.id, local)
        return doc
    except Exception as exc:  # noqa: BLE001 - never fail a run over its status
        print(f"[status] {product.id}: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        return None


def puts_per_day() -> dict[str, float]:
    """Worst-case Class A requests a day per tracked product, from the registry cadences (every run succeeds, every status differs)."""
    from algent_backend.ops.products import views

    out: dict[str, float] = {}
    for p in views.products():
        if not tracked(p):
            continue
        n = 0.0
        for j in p.job_list():
            if j.kind == "timer" and j.every_min:
                n += 1440 / j.every_min
        cad = cadence_min(p)
        if 0 < cad < 60:
            n = min(n, 1440 / MIN_GAP_MIN)
        out[p.id] = round(n, 1)
    return out
