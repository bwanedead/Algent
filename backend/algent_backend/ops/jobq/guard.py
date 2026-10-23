"""
The memory guard: a job does not start when ``MemAvailable - its expected peak`` would fall below the floor the resident services need.

- expected peak: the job's measured p95 peak RSS from the ledger (once ``MIN_SAMPLES`` runs exist), else the registry's ``est_mb``, else the class default;
- floor: for each resident service (AIS stream, SearXNG) how far it may still grow, i.e. its largest RSS the ledger ever sampled (else the documented default)
  minus its RSS now (services not seen running reserve nothing), plus ``SLACK_MB``; never below ``FLOOR_MIN_MB``. MemAvailable already excludes what the services hold today, so only their headroom is reserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import flags
from .ledger import stats


@dataclass(frozen=True)
class Verdict:
    ok: bool
    avail_mb: float | None
    need_mb: float
    floor_mb: float
    source: str                # where the expected peak came from: "ledger p95" / "registry estimate" / "class default"

    def reason(self) -> str:
        return (f"memory: {self.avail_mb:.0f} MB available - {self.need_mb:.0f} MB expected ({self.source}) < floor {self.floor_mb:.0f} MB"
                if self.avail_mb is not None else "memory: unknown")


def expected_mb(job: Any, rows: list[dict[str, Any]]) -> tuple[float, str]:
    st = stats(rows).get(job.name)
    if st and st["rss_samples"] >= flags.MIN_SAMPLES and st["rss_p95_mb"]:
        return float(st["rss_p95_mb"]), "ledger p95"
    if job.est_mb:
        return float(job.est_mb), "registry estimate"
    return flags.EST_MB[job.prio], "class default"


def service_peaks(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Largest RSS ever sampled per service (rows carry the ``svc`` sample taken at each job start), over the documented defaults."""
    peaks = dict(flags.SERVICE_PEAK_MB)
    for r in rows:
        for name, mb in (r.get("svc") or {}).items():
            peaks[name] = max(peaks.get(name, 0.0), float(mb))
    return peaks


def floor_mb(rows: list[dict[str, Any]], services_now: dict[str, float]) -> float:
    # Only services seen running: one we cannot find holds no memory we can see, and reserving for it would block jobs on a guess.
    peaks = service_peaks(rows)
    growth = sum(max(peaks.get(name, 0.0) - now, 0.0) for name, now in services_now.items())
    return max(growth + flags.SLACK_MB, flags.FLOOR_MIN_MB)


def check(job: Any, rows: list[dict[str, Any]], avail_mb: float | None, services_now: dict[str, float]) -> Verdict:
    need, source = expected_mb(job, rows)
    floor = floor_mb(rows, services_now)
    # A machine we cannot measure (a laptop) is never blocked; the guard exists for the server.
    return Verdict(avail_mb is None or avail_mb - need >= floor, avail_mb, need, floor, source)
