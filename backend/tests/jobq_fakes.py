"""A fake machine for the job queue: a clock that only moves when something sleeps, a lock another "process" can hold until a given time, scripted
memory and fake pids. Shared by the queue, hook and registry tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from algent_backend.ops.jobq.env import Env, _Nothing
from algent_backend.ops.jobq.ledger import Ledger
from algent_backend.ops.jobq.line import Entry, Line
from algent_backend.ops.jobq.runner import JobQueue

T0 = 1_760_000_000.0                       # 2025-10-09 08:53:20 UTC; tests that care about the time of day set their own start


class FakeEnv(Env):
    def __init__(self, home: Path, *, t: float = T0, mem: float | None = 3000.0, services: dict[str, float] | None = None) -> None:
        super().__init__(home)
        self.t, self.mem, self.services = t, mem, services if services is not None else {}
        self.held_until = 0.0                # another process holds the lock until this time
        self.mine = False                    # THIS process holds it
        self.alive = {4242}
        self.terminated: list[int] = []
        self.at: list[tuple[float, Any]] = []   # (time, callback) fired by sleep
        self.slept = 0

    # time moves only here
    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds
        self.slept += 1
        for when, cb in sorted(self.at, key=lambda x: x[0]):
            if when <= self.t:
                self.at.remove((when, cb))
                cb()

    def pid(self) -> int:
        return 4242

    def pid_alive(self, pid: int) -> bool:
        return pid in self.alive

    def terminate(self, pid: int) -> None:
        self.terminated.append(pid)

    def try_lock(self) -> Any | None:
        if self.mine or self.t < self.held_until:
            return None
        self.mine = True
        env = self

        class Handle(_Nothing):
            def close(self) -> None:
                env.mine = False

        return Handle()

    def mem_available_mb(self) -> float | None:
        return self.mem() if callable(self.mem) else self.mem

    def services_rss_mb(self) -> dict[str, float]:
        return dict(self.services)

    # scripting helpers
    def other_holds(self, job: str, *, until: float, prio: int = 1, pid: int = 900, preemptible: bool = False) -> None:
        """Another process (pid) runs ``job`` and holds the lock until ``until``."""
        self.held_until = until
        self.alive.add(pid)
        self.env_write_holder(job, prio, preemptible, pid)

        def release() -> None:
            self.remove(self.state_dir() / "holder.json")

        self.at.append((until, release))

    def env_write_holder(self, job: str, prio: int, preemptible: bool, pid: int) -> None:
        self.write_json(self.state_dir() / "holder.json", {"job": job, "prio": prio, "preemptible": preemptible, "since": self.t, "pid": pid})

    def other_waits(self, job: str, prio: int, *, pid: int = 901, deadline: float = 0.0, since: float | None = None) -> None:
        self.alive.add(pid)
        Line(self).join(Entry(job, prio, deadline, self.t if since is None else since, pid))


def queue(tmp_path: Path, **kw: Any) -> tuple[JobQueue, FakeEnv, Ledger]:
    env = FakeEnv(tmp_path, **kw)
    ledger = Ledger(tmp_path / "jobs.jsonl")
    return JobQueue(env, ledger), env, ledger
