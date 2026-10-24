"""The waiting line: who is queued for the job lock and who holds it, as small files (see ``env.py``). Pure bookkeeping, no policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .env import Env


@dataclass(frozen=True)
class Entry:
    job: str
    prio: int
    deadline: float            # epoch seconds, 0 = none
    since: float               # when it joined the line
    pid: int

    @property
    def key(self) -> tuple[float, float, float, str]:
        """Order of service: class, then the nearer deadline, then arrival."""
        return (self.prio, self.deadline or float("inf"), self.since, self.job)


class Line:
    def __init__(self, env: Env) -> None:
        self.env = env

    def _dir(self) -> Path:
        return self.env.state_dir() / "waiting"

    def waiting(self) -> list[Entry]:
        """Live waiters in service order; files of dead processes are removed on sight."""
        out = []
        for p in sorted(self._dir().glob("*.json")):
            d = self.env.read_json(p)
            try:
                e = Entry(str(d["job"]), int(d["prio"]), float(d["deadline"]), float(d["since"]), int(d["pid"]))  # type: ignore[index]
            except (TypeError, KeyError, ValueError):
                self.env.remove(p)
                continue
            if e.pid != self.env.pid() and not self.env.pid_alive(e.pid):
                self.env.remove(p)
                continue
            out.append(e)
        return sorted(out, key=lambda e: e.key)

    def join(self, entry: Entry) -> Entry | None:
        """Join the line. Returns the live entry of the SAME job that is already there (the caller coalesces into it), else None after joining."""
        for e in self.waiting():
            if e.job == entry.job and e.pid != entry.pid:
                return e
        self.env.write_json(self._dir() / f"{entry.job}.json", asdict(entry))
        return None

    def leave(self, job: str) -> None:
        self.env.remove(self._dir() / f"{job}.json")

    def ahead_of(self, me: Entry) -> list[Entry]:
        return [e for e in self.waiting() if e.job != me.job and e.key < me.key]

    # ── the holder ──
    def _holder(self) -> Path:
        return self.env.state_dir() / "holder.json"

    def set_holder(self, job: str, prio: int, preemptible: bool, since: float) -> None:
        self.env.write_json(self._holder(), {"job": job, "prio": prio, "preemptible": preemptible, "since": since, "pid": self.env.pid()})

    def clear_holder(self) -> None:
        self.env.remove(self._holder())

    def holder(self) -> dict[str, Any] | None:
        d = self.env.read_json(self._holder())
        if d and d.get("pid") != self.env.pid() and not self.env.pid_alive(int(d.get("pid") or 0)):
            return None
        return d
