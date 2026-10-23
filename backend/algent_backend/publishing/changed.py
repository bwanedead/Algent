"""
"Did this run change what we publish?" - the one signal behind a product's ``last_changed_at`` (``ops/status.py``, docs/architecture/foundation.md).

A job runner exports ``ALGENT_RUN_PRODUCT=<product id>`` to the job's process. The two uploaders (``object_docs.publish``, ``asset_store.upload``) call
``note`` with the keys that really went to the bucket (hash-skipped objects are not "changed"), and this module remembers the time per product in
``<held>/status/<product>.changed`` (a few bytes, no bucket request). A run that publishes nothing new leaves the file alone, which is exactly how a
sanctions run with no new designations stays "checked, not changed".

Staging publishes (``ALGENT_PUBLISH_TARGET=staging``) and the status documents themselves never count.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

ENV = "ALGENT_RUN_PRODUCT"
#: Keys that never count as the product changing: the status documents (they change every run by design) and the name indexes.
_IGNORED = ("status/", "docs/status/", "_names/", "docs/_names/")


def marker_path(product: str) -> Path:
    from . import object_store

    return object_store.held_dir() / "status" / f"{product}.changed"


def note(keys: Iterable[str], *, now: datetime | None = None) -> None:
    """Record that ``keys`` were uploaded by the running product's job. A no-op outside a runner and for staging; never raises."""
    keys = list(keys)
    product = os.environ.get(ENV, "").strip()
    if not product or os.environ.get("ALGENT_PUBLISH_TARGET", "").strip().lower() == "staging":
        return
    if not any(not k.lstrip("/").startswith(_IGNORED) for k in keys):
        return
    try:
        path = marker_path(product)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": (now or datetime.now(UTC)).isoformat(timespec="seconds")}), encoding="utf-8")
    except OSError:
        pass


def last_change(product: str) -> str:
    """ISO time of the newest recorded change for ``product`` ("" when none)."""
    try:
        return str(json.loads(marker_path(product).read_text(encoding="utf-8")).get("at") or "")
    except (OSError, ValueError, AttributeError):
        return ""
