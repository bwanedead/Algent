"""
``newsroom site smoke`` - ask a deployed site for everything it should serve and say what is wrong (docs/guides/deploy.md).

One implementation in Python, so the same code runs on the server (every hour against production, and after each publish), from the deploy routine
against a preview URL, and in tests with a fake fetcher. It makes about 60 requests, paced; it writes nothing on the site's side and its only local
state is the last report (``state.py``) for the doctor row.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from . import flags
from .checks import FAIL, OK, WARN, Result, judge
from .fetch import Fetch, Reply, default_fetch
from .probes import Probe, dynamic_probes, static_probes


@dataclass
class Report:
    base: str
    at: str
    results: list[Result] = field(default_factory=list)
    unsampled: list[str] = field(default_factory=list)       # dynamic route templates the sitemap gave no sample for (a note, not a failure)
    seconds: float = 0.0

    def count(self, severity: str) -> int:
        return sum(1 for r in self.results if r.severity == severity)

    @property
    def ok(self) -> bool:
        return self.count(FAIL) == 0 and bool(self.results)

    def p95_ms(self) -> int:
        times = sorted(r.ms for r in self.results)
        return times[min(len(times) - 1, int(len(times) * 0.95))] if times else 0

    def summary(self) -> str:
        slow = max(self.results, key=lambda r: r.ms, default=None)
        return (f"{len(self.results)} checks: {self.count(OK)} ok, {self.count(WARN)} warn, {self.count(FAIL)} fail; "
                f"p95 {self.p95_ms()} ms" + (f", slowest {slow.path} {slow.ms} ms" if slow else "") + f"; {self.seconds:.0f} s")

    def problems(self) -> list[Result]:
        return sorted((r for r in self.results if r.severity != OK), key=lambda r: (r.severity != FAIL, r.path))

    def text(self) -> str:
        lines = [f"smoke {self.base} - {'OK' if self.ok else 'FAILED'} - {self.summary()}"]
        lines += [f"  {r.severity.upper():<4} {r.path} [{r.status} {r.ms} ms]: {'; '.join(r.notes)}" for r in self.problems()]
        if self.unsampled:
            lines.append(f"  note: no sample for {', '.join(self.unsampled)}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {"base": self.base, "at": self.at, "ok": self.ok, "summary": self.summary(), "seconds": round(self.seconds, 1),
                "counts": {s: self.count(s) for s in (OK, WARN, FAIL)}, "p95_ms": self.p95_ms(), "unsampled": self.unsampled,
                "problems": [r.as_dict() for r in self.problems()], "results": [r.as_dict() for r in self.results]}


def normalise(base: str) -> str:
    base = base.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ValueError(f"--base must be an http(s) URL, got {base!r}")
    return base


def run(base: str | None = None, *, fetch: Fetch = default_fetch, now: datetime | None = None, pace: float = flags.PACE_S,
        sleep: Callable[[float], None] = time.sleep) -> Report:
    """Check every probe against ``base`` (default: production). Never raises: a request that cannot be made is a failed check."""
    base = normalise(base or flags.PRODUCTION_BASE)
    now = now or datetime.now(UTC)
    t0 = time.monotonic()
    report = Report(base=base, at=now.isoformat(timespec="seconds"))
    probes = static_probes()
    replies: dict[str, Reply] = {}

    def ask(probe: Probe) -> None:
        if replies:
            sleep(pace)
        try:
            reply = fetch(base + probe.path)
        except Exception as exc:  # noqa: BLE001 - a broken fetcher is a failed check, not a crashed job
            reply = Reply(0, error=f"{type(exc).__name__}: {str(exc)[:120]}")
        replies[probe.path] = reply
        report.results.append(judge(probe, reply, now=now))

    sitemap = next(p for p in probes if p.path == "/sitemap.xml")
    ask(sitemap)
    sample, report.unsampled = dynamic_probes(replies["/sitemap.xml"].text() if replies["/sitemap.xml"].status == 200 else "")
    for probe in [p for p in probes if p is not sitemap] + sample:
        ask(probe)
    report.seconds = time.monotonic() - t0
    return report
