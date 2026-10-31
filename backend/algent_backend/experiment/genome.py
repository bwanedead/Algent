"""
One-change children of a protocol. A protocol is a composition of policy versions (its genome); a child changes exactly ONE of them and names the parent, so the
genealogy (``genealogy.tree``) shows precisely what was varied. Used by ``mutate`` (the proposer) and ``tournament`` (candidates given as a spec).

Spec grammar for a candidate: ``BASE`` (a named mind such as ``p0b+prior``, or a stored protocol id/name) followed by ONE optional change,
``BASE;calibration=platt``, ``BASE;evidence=keyword-overlap@1``, ``BASE;k=4``. More than one change is refused: a candidate that varies two things teaches nothing.
"""

from __future__ import annotations

from typing import Any

from . import calibration, controls, flags, genealogy, policies, store
from . import research_policy as rp
from .contracts import PolicyVersion, Protocol

K_KNOB = "rows_per_query"        # the evidence-size knob of the planned research policy; snapshot retrievers use ``k``


def child(proto: Protocol, new: PolicyVersion, name: str) -> Protocol:
    """``proto`` with ONE policy replaced, named ``name``. If that exact composition is already stored (under any name) it is returned as it is."""
    kinds = {k: v for k, v in proto.policies.items() if k != new.kind}
    pid = store.digest({k: v.digest for k, v in sorted({**kinds, new.kind: new}.items())})
    if store.exists(f"protocols/{pid}.json"):
        return policies.load_protocol(pid)
    return policies.replace_policy(proto, new, name)


def evidence_alternatives(proto: Protocol) -> list[PolicyVersion]:
    """Every registered evidence policy other than the one in use: the snapshot retrievers and production's planned research."""
    cur = proto.policies["evidence"]
    alts = [policies.evidence_policy(n, v, k=int(cur.params.get("k", 8))) for (n, v) in sorted(policies.RETRIEVERS)] + [controls.production_research_policy()]
    return [a for a in alts if (a.name, a.version) != (cur.name, cur.version)]


def with_evidence(proto: Protocol, ref: str) -> Protocol:
    name, _, ver = ref.partition("@")
    pick = next((a for a in evidence_alternatives(proto) if (a.name, str(a.version)) == (name, ver or "1")), None)
    if pick is None:
        raise KeyError(f"no evidence policy {ref!r} to swap to (it may already be in use)")
    return child(proto, pick, f"{proto.name}~{pick.name}")


def k_variants(proto: Protocol) -> list[tuple[int, PolicyVersion]]:
    """The evidence-size changes worth trying: half and double the current size (never below 2)."""
    cur = proto.policies["evidence"]
    planned = policies.is_planned(cur)
    key = K_KNOB if planned else "k"
    now = int(cur.params.get(key, flags.EVIDENCE_K))
    out = []
    for k in sorted({max(2, now // 2), now * 2} - {now}):
        pv = (policies.make("evidence", rp.NAME, rp.VERSION, {**cur.params, key: k}, controls._research_impl()) if planned
              else policies.make("evidence", cur.name, cur.version, {**cur.params, "k": k}, policies.RETRIEVERS[(cur.name, cur.version)]))
        out.append((k, pv))
    return out


def with_k(proto: Protocol, k: int) -> Protocol:
    pick = next((pv for kk, pv in k_variants(proto) if kk == k), None)
    if pick is None:
        raise ValueError(f"evidence size {k} is not half or double the current one")
    return child(proto, pick, f"{proto.name}~k{k}")


def with_calibration(proto: Protocol, name: str, live_strategies: tuple[str, ...] = ()) -> Protocol:
    return child(proto, calibration.named(name, live_strategies), f"{proto.name}~{name}")


def load(ref: str) -> Protocol:
    """A protocol from a named mind (``p0b``, ``b+prior``...) or a stored protocol id, id prefix or name."""
    from . import qset

    return qset.protocol_named(ref) if ref in qset.NAMED else policies.load_protocol(genealogy.resolve(ref))


def parse(spec: str) -> Protocol:
    """A candidate protocol from a spec (see the module docstring)."""
    base, *changes = [x.strip() for x in spec.split(";") if x.strip()]
    if len(changes) > 1:
        raise ValueError(f"{spec!r} varies more than one thing; a candidate changes exactly one policy")
    proto = load(base)
    if not changes:
        return proto
    key, _, val = changes[0].partition("=")
    if key == "calibration":
        return with_calibration(proto, val)
    if key == "evidence":
        return with_evidence(proto, val)
    if key == "k":
        return with_k(proto, int(val))
    raise ValueError(f"unknown change {key!r} in {spec!r} (calibration=, evidence=, k=)")


def describe(proto: Protocol) -> dict[str, Any]:
    parent = policies.load_protocol(proto.parent) if proto.parent and store.exists(f"protocols/{proto.parent}.json") else None
    return {"id": proto.id, "name": proto.name, "parent": proto.parent, "changed": genealogy.changed(proto, parent)}
