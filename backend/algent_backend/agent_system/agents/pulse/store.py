"""
The Pulse store — situations, Pulse definitions, append-only influence logs, and watches.

Layout under ``ALGENT_PULSE_STORE`` (default ``pulse_store/``, local like the profile store):

    situations/<situation_id>.json
    pulses/<pulse_id>.json          definition history (versions appended, never edited)
    log/<pulse_id>.jsonl            influences — append-only, one JSON object per line
    watches/<watch_id>.json         status moves only open → a terminal state, once

Invariants the store enforces (a Pulse's history is the valuable part, so it defends it):
- an influence is never rewritten or removed, and one with a key already in the log is refused;
- an influence must name a definition version the Pulse actually has;
- a definition is changed by appending a new version, never by editing the old one;
- a resolved watch cannot be reopened or re-resolved.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from .contracts import Event, Influence, Pulse, PulseDefinition, Situation, Watch, influence_key
from .projection import PulseState, project

_STORE_ENV = "ALGENT_PULSE_STORE"
_DEFAULT_DIR = "pulse_store"


class DuplicateInfluence(ValueError):
    """The same assessment act was appended twice (a retried run)."""


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "x"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PulseStore:
    def __init__(self, base_dir: Path | str | None = None) -> None:
        self._dir = Path(base_dir or os.environ.get(_STORE_ENV) or _DEFAULT_DIR)

    @property
    def root(self) -> Path:
        return self._dir

    # ── situations ────────────────────────────────────────────────────────────────────────────
    def save_situation(self, situation: Situation) -> None:
        if not situation.created_at:
            situation = situation.model_copy(update={"created_at": _now()})
        self._write(self._dir / "situations" / f"{_safe(situation.id)}.json",
                    situation.model_dump())

    def situation(self, situation_id: str) -> Situation | None:
        return self._read(self._dir / "situations" / f"{_safe(situation_id)}.json", Situation)

    def situations(self) -> list[Situation]:
        return [s for s in (self._read(p, Situation) for p in self._glob("situations"))
                if s is not None]

    # ── pulses and their versioned definitions ───────────────────────────────────────────────
    def create_pulse(self, pulse: Pulse) -> None:
        path = self._pulse_path(pulse.id)
        if path.exists():
            raise ValueError(f"pulse {pulse.id} already exists — add a definition version instead")
        if not pulse.definitions:
            raise ValueError(f"pulse {pulse.id} has no definition (no ruler to assess against)")
        defs = [d.model_copy(update={"version": i, "created_at": d.created_at or _now()})
                for i, d in enumerate(pulse.definitions, 1)]
        self._write(path, pulse.model_copy(update={"definitions": defs}).model_dump())
        sit = self.situation(pulse.situation_id)
        if sit is not None and pulse.id not in sit.pulse_ids:
            self.save_situation(sit.model_copy(update={"pulse_ids": [*sit.pulse_ids, pulse.id]}))

    def add_definition(self, pulse_id: str, definition: PulseDefinition) -> int:
        """Improve the ruler: append a new version. Returns its number."""
        pulse = self._require(pulse_id)
        version = pulse.definition.version + 1
        new = definition.model_copy(update={"version": version, "created_at": _now()})
        self._write(self._pulse_path(pulse_id),
                    pulse.model_copy(update={"definitions": [*pulse.definitions, new]}).model_dump())
        return version

    def set_status(self, pulse_id: str, status: str) -> None:
        pulse = self._require(pulse_id)
        self._write(self._pulse_path(pulse_id), pulse.model_copy(update={"status": status}).model_dump())

    def pulse(self, pulse_id: str) -> Pulse | None:
        return self._read(self._pulse_path(pulse_id), Pulse)

    def pulses(self, situation_id: str | None = None) -> list[Pulse]:
        found = [p for p in (self._read(x, Pulse) for x in self._glob("pulses")) if p is not None]
        return [p for p in found if situation_id is None or p.situation_id == situation_id]

    # ── the influence log (append-only) ──────────────────────────────────────────────────────
    def append(self, influence: Influence) -> Influence:
        """Append one influence. Refuses duplicates and unknown definition versions."""
        pulse = self._require(influence.pulse_id)
        versions = {d.version for d in pulse.definitions}
        if influence.definition_version not in versions:
            raise ValueError(f"{influence.pulse_id} has no definition v{influence.definition_version}")
        pos = influence.proposed_position
        if pos is not None and not 0.0 <= pos <= 100.0:
            raise ValueError(f"position {pos} is off the 0–100 ruler")
        if not influence.key:
            src = influence.source
            influence = influence.model_copy(update={"key": influence_key(
                influence.pulse_id, src.event_id, src.run_id, influence.mode)})
        if any(i.key == influence.key for i in self.log(influence.pulse_id)):
            raise DuplicateInfluence(f"{influence.key} already in {influence.pulse_id}'s log")
        path = self._dir / "log" / f"{_safe(influence.pulse_id)}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(influence.model_dump(), ensure_ascii=False) + "\n")
        return influence

    def log(self, pulse_id: str) -> list[Influence]:
        path = self._dir / "log" / f"{_safe(pulse_id)}.jsonl"
        if not path.is_file():
            return []
        return [Influence.model_validate_json(line)
                for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def state(self, pulse_id: str, *, as_of: str | None = None) -> PulseState:
        return project(pulse_id, self.log(pulse_id), as_of=as_of)

    # ── events ───────────────────────────────────────────────────────────────────────────────
    def record_event(self, event: Event) -> Event:
        """Create the event, or merge a new sighting (situations, sources) into the existing one."""
        path = self._dir / "events" / f"{_safe(event.id)}.json"
        old = self._read(path, Event)
        if old is not None:
            event = old.model_copy(update={
                "situation_ids": list(dict.fromkeys([*old.situation_ids, *event.situation_ids])),
                "sources": [*old.sources, *[s for s in event.sources if s not in old.sources]]})
        self._write(path, event.model_dump())
        return event

    def event(self, event_id: str) -> Event | None:
        return self._read(self._dir / "events" / f"{_safe(event_id)}.json", Event)

    # ── watches ──────────────────────────────────────────────────────────────────────────────
    def save_watch(self, watch: Watch) -> None:
        path = self._dir / "watches" / f"{_safe(watch.id)}.json"
        if path.exists():
            raise ValueError(f"watch {watch.id} exists — resolve it, do not overwrite it")
        self._write(path, watch.model_copy(update={"created_at": watch.created_at or _now()}).model_dump())

    def resolve_watch(self, watch_id: str, status: str, *, by=None) -> Watch:
        path = self._dir / "watches" / f"{_safe(watch_id)}.json"
        watch = self._read(path, Watch)
        if watch is None:
            raise KeyError(watch_id)
        if watch.status != "open":
            raise ValueError(f"watch {watch_id} is already {watch.status}")
        if status not in ("triggered", "expired", "invalidated"):
            raise ValueError(f"not a terminal status: {status}")
        done = watch.model_copy(update={"status": status, "resolved_at": _now(), "resolved_by": by})
        self._write(path, done.model_dump())
        return done

    def watches(self, situation_id: str | None = None) -> list[Watch]:
        found = [w for w in (self._read(p, Watch) for p in self._glob("watches")) if w is not None]
        return [w for w in found if situation_id is None or w.situation_id == situation_id]

    # ── plumbing ─────────────────────────────────────────────────────────────────────────────
    def _pulse_path(self, pulse_id: str) -> Path:
        return self._dir / "pulses" / f"{_safe(pulse_id)}.json"

    def _require(self, pulse_id: str) -> Pulse:
        pulse = self.pulse(pulse_id)
        if pulse is None:
            raise KeyError(f"no pulse {pulse_id}")
        return pulse

    def _glob(self, sub: str) -> list[Path]:
        folder = self._dir / sub
        return sorted(folder.glob("*.json")) if folder.is_dir() else []

    @staticmethod
    def _read(path: Path, model):
        if not path.is_file():
            return None
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                       newline="\n")
        tmp.replace(path)
