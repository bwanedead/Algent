"""
Who is the runner? One machine at a time runs paid work and publishes; this file says which.

Ohmega can run on the worker server OR the operator's laptop, but never both at once: two machines writing
the stores and publishing would fork the corpus. The claim is a tiny ``runner.json`` at the root of the private
``algent-data`` archive (the same repo ``sync`` already mirrors the stores into), so it needs no migration and
works with the database unset. It travels the same git remote as the stores, so both machines see it.

Design choices (deliberately mechanical):
- A CLAIM IS ADVISORY, NOT A LOCK. Handover is a human act (``release`` then ``claim``); the guard exists to
  stop the mistake of running on the wrong machine, not to defeat a determined operator.
- THE GUARD FAILS OPEN. It refuses only when the archive positively names a DIFFERENT host. Archive unreachable,
  record missing, backups disabled (tests) -> allow. Being locked out of your own pipeline because GitHub
  hiccuped is worse than the rare double-run. ``ALGENT_RUNNER_GUARD=0`` switches it off.
- STALE CLAIM (the server died holding it): ``newsroom runner claim --force`` takes it over.
- Never raises out of the guard path.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from typing import Any

from . import sync

FILENAME = "runner.json"
_GUARD_ENV = "ALGENT_RUNNER_GUARD"
_NAME_ENV = "ALGENT_RUNNER_NAME"


def this_host() -> str:
    return (os.environ.get(_NAME_ENV) or socket.gethostname()).strip() or "unknown"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def guard_enabled() -> bool:
    return sync.enabled() and os.environ.get(_GUARD_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _read(wt) -> dict[str, Any]:
    try:
        data = json.loads((wt / FILENAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def status() -> dict[str, Any]:
    """``{runner: host|None, since, this_host, is_runner, reachable, note}``. Never raises."""
    me = this_host()
    try:
        wt, how = sync._checkout()
    except Exception as exc:  # noqa: BLE001
        wt, how = None, type(exc).__name__
    if wt is None:
        return {"runner": None, "this_host": me, "is_runner": False, "reachable": False, "note": how}
    rec = _read(wt)
    host = rec.get("host") or None
    return {"runner": host, "since": rec.get("claimed_at"), "this_host": me, "is_runner": host == me,
            "reachable": True, "note": rec.get("note", "")}


def _write(record: dict[str, Any], message: str) -> dict[str, Any]:
    wt, how = sync._checkout()
    if wt is None:
        return {"ok": False, "note": f"archive unreachable: {how}"}
    (wt / FILENAME).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    sync._git(wt, "add", FILENAME)
    ok, out = sync._git(wt, "commit", "-m", message)
    if not ok and "nothing to commit" not in out:
        return {"ok": False, "note": f"commit failed: {out[:160]}"}
    ok, out = sync._git(wt, "push", "-u", "origin", sync.BRANCH)
    if not ok:  # someone else moved the archive: rebase our one commit on top and try once more
        rebased, _ = sync._git(wt, "pull", "--rebase", "origin", sync.BRANCH)
        if rebased:
            ok, out = sync._git(wt, "push", "-u", "origin", sync.BRANCH)
        else:
            sync._git(wt, "rebase", "--abort")
    return {"ok": ok, "note": "recorded" if ok else f"push failed: {out[:160]}"}


def claim(*, force: bool = False, note: str = "") -> dict[str, Any]:
    """Make this machine the runner. Refuses while another host holds it, unless ``force``."""
    cur = status()
    if not cur["reachable"]:
        return {"claimed": False, "note": f"cannot read the archive ({cur['note']}); not claiming blind"}
    holder = cur["runner"]
    if holder and holder != cur["this_host"] and not force:
        return {"claimed": False, "runner": holder, "since": cur.get("since"),
                "note": f"{holder} holds the runner claim. Release it there, or if that machine is gone "
                        "re-run with --force."}
    record = {"host": cur["this_host"], "claimed_at": _now(), "note": note}
    if holder and holder != cur["this_host"]:
        record["took_over_from"] = holder
    res = _write(record, f"runner: claim by {cur['this_host']}")
    return {"claimed": res["ok"], "runner": cur["this_host"] if res["ok"] else holder, "note": res["note"]}


def release(*, force: bool = False) -> dict[str, Any]:
    """Give the claim up. Only the holder may release, unless ``force`` (holder is gone)."""
    cur = status()
    if not cur["reachable"]:
        return {"released": False, "note": f"cannot read the archive ({cur['note']})"}
    holder = cur["runner"]
    if holder and holder != cur["this_host"] and not force:
        return {"released": False, "runner": holder,
                "note": f"{holder} holds it, not this machine. Release it there, or --force if it is gone."}
    if not holder:
        return {"released": True, "note": "nobody held the claim"}
    res = _write({"host": None, "released_at": _now(), "released_by": cur["this_host"]},
                 f"runner: release by {cur['this_host']}")
    return {"released": res["ok"], "note": res["note"]}


def refusal(action: str) -> str | None:
    """None when this machine may run ``action``; otherwise the sentence to show. Fails open (see module doc)."""
    if not guard_enabled():
        return None
    try:
        cur = status()
    except Exception:  # noqa: BLE001
        return None
    if not cur["reachable"] or not cur["runner"] or cur["is_runner"]:
        return None
    return (f"refusing to {action}: {cur['runner']} is the runner (since {cur.get('since')}), and this machine "
            f"is {cur['this_host']}. Hand over with `newsroom runner release` there then `newsroom runner claim` "
            "here (add --force if that machine is gone), or set ALGENT_RUNNER_GUARD=0 for a one-off.")
