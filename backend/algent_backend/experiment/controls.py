"""
Frozen controls beyond the blind forecaster. Each ``freeze_*`` copies production AS IT IS NOW into the store once (a pointer under ``frozen/``) and later calls
return the stored capture, whatever the code says. A new freeze never edits an old one: it is a NEW protocol that names the one it supersedes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from algent_backend.markets import research as rs

from . import policies, store
from . import research_policy as rp
from .contracts import PolicyVersion, Protocol
from .cutoff_corpus import CutoffCorpus


def _research_impl() -> list[Callable[..., Any]]:
    return [rp.retrieve, rp._to_evidence, CutoffCorpus, rs.research, rs.run_query, rs._blocked]


def production_research_policy() -> PolicyVersion:
    return policies.make("evidence", rp.NAME, rp.VERSION, rp.captured_params(), _research_impl())


def freeze_production_research() -> Protocol:
    """P0b: the frozen blind forecaster with production's model-planned corpus research as its evidence policy (cutoff-bounded). Supersedes P0, which stays as it is."""
    ptr = store.read_json("frozen/p0-research.json")
    if ptr:
        return policies.load_protocol(ptr["protocol_id"])
    p0 = policies.freeze_blind_forecaster()
    proto = policies.replace_policy(p0, production_research_policy(), "p0b-production-research-frozen")
    store.write_once("frozen/p0-research.json", {"protocol_id": proto.id, "supersedes": p0.id, "captured_at": store.now_iso(), "from": "markets/research.py",
                                                 "note": "same prompt, model and bounds as P0; the evidence policy is production's planned corpus research over a cutoff-bounded view"})
    return proto


def impl_drift(proto: Protocol) -> dict[str, dict[str, str]]:
    """Evidence policies whose code changed since they were frozen: stored ``impl_sha`` vs the code now. Empty = the control still runs what it was captured with."""
    pv = proto.policies.get("evidence")
    if pv is None or not pv.impl_sha:
        return {}
    fns = _research_impl() if policies.is_planned(pv) else [policies.RETRIEVERS[(pv.name, pv.version)]]
    now = policies.sha_of(*fns)
    return {} if now == pv.impl_sha else {pv.ref: {"frozen": pv.impl_sha, "now": now}}
