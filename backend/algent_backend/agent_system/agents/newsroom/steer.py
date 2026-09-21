"""
Operator steer — change a run's framing while it is running, without starting over.

The rail used to take its framing once, from ``--angle`` at launch. Clarifying it meant killing
the run: the Greenland piece was relaunched two minutes in to move from "establish the deal" to
"read it as strategy", and the research the new framing would happily have reused was thrown
away with it. Framing clarifications are cheap and common; a profile is not.

How it works
------------
``newsroom steer "..."`` appends a note to a PENDING file. The running rail drains that file at
every stage boundary — the same place it checks for a pause — into the run's own
``artifacts/steer.jsonl``, so the steer is persisted with the run it shaped and a resumed run
carries it forward. From then on the steer rides into every later stage: the profile research
(if it has not started yet) sees it beside the vector's thesis, and everything after research
reads it at the top of the profile briefing.

What it deliberately does NOT do is reopen a stage that has already finished. Research done under
the old framing is almost always still the material the new framing needs — that is the point —
and a steer that silently re-ran research would cost exactly what it exists to save. If a steer
needs different evidence, that is a new run.

A steer is framing, never evidence: it says what to emphasise and how to read the material, and
it adds no facts to the ledger.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PENDING = Path("runs_data") / "newsroom_steer.pending.jsonl"
RUN_FILE = "steer.jsonl"


def add(text: str, *, path: Path | None = None) -> dict[str, Any]:
    """Queue a steer for the live run (or the next one, if none is running)."""
    note = " ".join((text or "").split())
    if not note:
        raise ValueError("a steer needs some words")
    entry = {"text": note, "at": datetime.now(UTC).isoformat()}
    target = path or PENDING
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def pending(*, path: Path | None = None) -> list[dict[str, Any]]:
    return _read(path or PENDING)


def clear_pending(*, path: Path | None = None) -> None:
    (path or PENDING).unlink(missing_ok=True)


def drain(run_artifacts: Path, *, stage: str = "", path: Path | None = None) -> list[dict[str, Any]]:
    """Move pending steers into this run's own file. Returns what was moved.

    Stamped with the stage it arrived before, so the record shows which work it could and could
    not have shaped. Never raises: a steer that fails to land must not kill a run.
    """
    source = path or PENDING
    entries = _read(source)
    if not entries:
        return []
    try:
        run_artifacts.mkdir(parents=True, exist_ok=True)
        with (run_artifacts / RUN_FILE).open("a", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps({**e, "before_stage": stage}, ensure_ascii=False) + "\n")
        source.unlink(missing_ok=True)
    except OSError:
        return []
    return entries


def for_run(run_artifacts: Path | None) -> list[str]:
    """Every steer this run has received, oldest first."""
    if run_artifacts is None:
        return []
    return [str(e.get("text") or "") for e in _read(run_artifacts / RUN_FILE) if e.get("text")]


def apply_to_vector(vector: dict[str, Any], steers: list[str]) -> dict[str, Any]:
    """The vector research starts from, with the steers after its thesis."""
    if not steers:
        return vector
    thesis = str(vector.get("thesis") or "").strip()
    added = "\n".join(f"- {s}" for s in steers)
    return {**vector, "thesis": f"{thesis}\n\nOPERATOR STEER (added while running):\n{added}".strip()}


def apply_to_profile(profile: dict[str, Any], steers: list[str]) -> dict[str, Any]:
    if not steers or not profile:
        return profile
    return {**profile, "operator_steer": list(steers)}


def _read(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out
