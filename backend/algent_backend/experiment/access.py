"""
The information-access gate. A protocol sees evidence only through a ``Reader``; the reader re-checks every record on every read, so a policy cannot
widen what it was given. Rules (docs/architecture/experiment-framework.md, "Information access"):

  evidence      visible iff publish_time <= cutoff and (acquired_at unknown or <= cutoff). An unknown publish time is never visible.
  observation   shared (L2): derived_at <= cutoff AND every source id visible. Branch-private (L3): only to that branch, and only when as_of <= cutoff.
                A summary made after the cutoff is excluded even if it only mentions older things: derivation can import hindsight.
  branches      one branch can never read another's memory or conclusions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .contracts import Evidence, Observation
from .store import parse_time


class AccessDenied(Exception):
    pass


def evidence_ok(ev: Evidence, cutoff: str) -> str:
    """Empty if visible, else the reason it is not."""
    c, p, a = parse_time(cutoff), parse_time(ev.publish_time), parse_time(ev.acquired_at)
    if c is None:
        return "no cutoff"
    if p is None:
        return "publish time unknown"
    if p > c:
        return "published after cutoff"
    if a is not None and a > c:
        return "acquired after cutoff"
    return ""


def filter_evidence(items: Iterable[Evidence], cutoff: str) -> tuple[list[Evidence], list[tuple[str, str]]]:
    seen: set[str] = set()
    out: list[Evidence] = []
    skipped: list[tuple[str, str]] = []
    for ev in items:
        if ev.id in seen:
            continue
        seen.add(ev.id)
        why = evidence_ok(ev, cutoff)
        if why:
            skipped.append((ev.id, why))
        else:
            out.append(ev)
    return out, skipped


def observation_ok(ob: Observation, cutoff: str, branch: str, visible_ids: set[str], lookup: Callable[[str], Observation | None] | None = None,
                   _depth: int = 0) -> str:
    c = parse_time(cutoff)
    if not ob.source_ids or not ob.method or not ob.method_version:
        return "derived object without source or method"
    if ob.branch:
        if ob.branch != branch:
            return "private to another branch"
        a = parse_time(ob.as_of)
        return "" if a is not None and c is not None and a <= c else "formed after cutoff"
    d = parse_time(ob.derived_at)
    if c is None or d is None or d > c:
        return "derived after cutoff"
    for sid in ob.source_ids:
        if sid in visible_ids:
            continue
        parent = lookup(sid) if lookup and _depth < 8 else None          # a source may itself be an observation: closure over the chain
        if parent is None or observation_ok(parent, cutoff, branch, visible_ids, lookup, _depth + 1):
            return f"source {sid} not visible"
    return ""


class Reader:
    """The only door a policy gets to the world. Built per (cutoff, branch); read-only."""

    def __init__(self, evidence: Iterable[Evidence], observations: Iterable[Observation], memory: Iterable[Observation], *, cutoff: str, branch: str):
        self.cutoff, self.branch = cutoff, branch
        self._ev, self.excluded = filter_evidence(evidence, cutoff)
        ok = {e.id for e in self._ev}
        obs = list(observations)
        by_id = {o.id: o for o in obs}
        self._obs = [o for o in obs if not observation_ok(o, cutoff, branch, ok, by_id.get)]
        self._mem = [m for m in memory if m.branch == branch and not observation_ok(m, cutoff, branch, ok, by_id.get)]

    def evidence(self) -> list[Evidence]:
        return [e for e in self._ev if not evidence_ok(e, self.cutoff)]

    def observations(self) -> list[Observation]:
        return list(self._obs)

    def memory(self) -> list[Observation]:
        return list(self._mem)
