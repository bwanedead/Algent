"""
Versioned policies and protocols. A policy version is content-addressed (digest of kind, name, version, params) and stored write-once; a protocol is a
composition of policy versions, also write-once. Changing anything means making a NEW policy version and a new protocol; nothing is edited in place.

``freeze_blind_forecaster`` snapshots today's blind forecaster (markets/forecast.py) AS IT IS NOW: its role text, task format, model settings and bounds are
copied into the store, and a run reads them from there, never from the live module. That is the control: later edits to forecast.py cannot change it.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from collections.abc import Callable
from typing import Any

from . import flags, store
from . import research_policy as rp
from .contracts import POLICY_KINDS, Evidence, PolicyVersion, Protocol, Question

#: Transcribed from ``markets.forecast.task_for`` at capture; ``tests/test_experiment_lab.py`` pins that they render alike, so drift in production shows up.
TASK_TEMPLATE = ("TODAY: {today}\n\nQUESTION: {question}\nENDS: {ends}\n\nRESOLUTION RULES (the market's own text):\n{rules}\n\n"
                 "WHAT THE DESK KNOWS:\n{evidence}\n\nTASK: the probability this resolves YES, with a brief rationale and the evidence ids you used.")
NO_EVIDENCE = "(The desk holds nothing relevant to this question. Say so and use base rates.)"
Retriever = Callable[[list[Evidence], Question, dict[str, Any]], list[Evidence]]


def sha_of(*fns: Callable[..., Any]) -> str:
    """Hash of the source of the code a policy runs (several functions or classes are hashed together; one gives the same hash it always did)."""
    return hashlib.sha256("\n".join(inspect.getsource(f) for f in fns).encode("utf-8")).hexdigest()[:12]


def make(kind: str, name: str, version: int, params: dict[str, Any] | None = None, impl: Callable[..., Any] | list[Callable[..., Any]] | None = None) -> PolicyVersion:
    if kind not in POLICY_KINDS:
        raise ValueError(f"unknown policy kind {kind!r}")
    fns = impl if isinstance(impl, list) else [impl] if impl else []
    pv = PolicyVersion(kind=kind, name=name, version=version, params=params or {}, impl_sha=sha_of(*fns) if fns else "")
    pv.digest = store.digest({"kind": kind, "name": name, "version": version, "params": pv.params, "impl": pv.impl_sha})
    store.write_once(f"policies/{pv.digest}.json", pv)
    return pv


# ── evidence-retrieval policies (code; a changed implementation is a new version) ─────────────────
def recent_k(items: list[Evidence], q: Question, params: dict[str, Any]) -> list[Evidence]:
    """The newest ``k`` visible documents by publish time. No relevance judgement."""
    return sorted(items, key=lambda e: (e.publish_time, e.id), reverse=True)[: int(params["k"])]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower())}


def keyword_overlap(items: list[Evidence], q: Question, params: dict[str, Any]) -> list[Evidence]:
    """The ``k`` visible documents sharing most distinctive words with the question and its rules (ties: newer first); documents sharing none are dropped."""
    want = _words(q.text + " " + q.rules)
    scored = [(len(want & _words(e.title + " " + e.body)), e) for e in items]
    ranked = sorted((s for s in scored if s[0] > 0), key=lambda s: (s[0], s[1].publish_time, s[1].id), reverse=True)
    return [e for _, e in ranked[: int(params["k"])]]


RETRIEVERS: dict[tuple[str, int], Retriever] = {("recent-k", 1): recent_k, ("keyword-overlap", 1): keyword_overlap}


def retriever(pv: PolicyVersion) -> Retriever:
    return RETRIEVERS[(pv.name, pv.version)]


def is_planned(pv: PolicyVersion) -> bool:
    """A policy that plans its own retrieval with a model call over the corpus (``research_policy``), instead of ranking the snapshot's documents."""
    return pv.kind == "evidence" and (pv.name, pv.version) == (rp.NAME, rp.VERSION)


def evidence_policy(name: str, version: int = 1, k: int = flags.EVIDENCE_K, body_chars: int = flags.BODY_CHARS) -> PolicyVersion:
    return make("evidence", name, version, {"k": k, "body_chars": body_chars}, RETRIEVERS[(name, version)])


# ── protocols ─────────────────────────────────────────────────────────────────────────────────────
def compose(name: str, policies: list[PolicyVersion], parent: str = "") -> Protocol:
    by_kind = {p.kind: p for p in policies}
    if len(by_kind) != len(policies):
        raise ValueError("one policy per kind")
    proto = Protocol(id=store.digest({k: v.digest for k, v in sorted(by_kind.items())}), name=name, policies=by_kind, parent=parent)
    store.write_once(f"protocols/{proto.id}.json", proto)
    return proto


def load_protocol(pid: str) -> Protocol:
    raw = store.read_json(f"protocols/{pid}.json")
    if raw is None:
        raise KeyError(f"unknown protocol {pid}")
    return Protocol.model_validate(raw)


def replace_policy(proto: Protocol, new: PolicyVersion, name: str) -> Protocol:
    """A new protocol equal to ``proto`` except for one policy. The original is untouched."""
    return compose(name, [*(p for k, p in proto.policies.items() if k != new.kind), new], parent=proto.id)


def freeze_blind_forecaster() -> Protocol:
    """P0: today's blind forecaster, captured as-is (once; later calls return the stored snapshot, whatever the code says now)."""
    ptr = store.read_json("frozen/p0.json")
    if ptr:
        return load_protocol(ptr["protocol_id"])
    from algent_backend.markets import flags as mf
    from algent_backend.markets import forecast as fc

    research = bool(mf.RESEARCH_ENABLED and mf.CORPUS_ONLY)
    role = fc.ROLE + (fc.RESEARCH_ADDENDUM if mf.RESEARCH_ENABLED else "")
    prompts = make("prompts", "blind-forecast", 1, {"prompt_version": fc.PROMPT_VERSION_RESEARCH if research else fc.PROMPT_VERSION, "role": role,
                                                    "task_template": TASK_TEMPLATE, "no_evidence": NO_EVIDENCE,
                                                    "output_fields": list(fc.ForecastOut.model_fields)})
    model = make("model", "house-low", 1, {"spec": "house", "effort": "low", "temperature": 0.2, "max_tokens": 2048, "cap_usd": mf.FORECAST_CALL_CAP_USD})
    prediction = make("prediction", "probability-yes", 1, {"p_min": mf.P_MIN, "p_max": mf.P_MAX, "invalid_is_abstention": True})
    memory = make("memory", "branch-notes", 1, {"write": True, "inject_into_prompt": False})
    tools = make("tools", "none", 1, {})
    proto = compose("p0-blind-forecaster-frozen", [prompts, model, prediction, memory, tools, evidence_policy("recent-k")])
    store.write_once("frozen/p0.json", {"protocol_id": proto.id, "captured_at": store.now_iso(), "from": "markets/forecast.py",
                                        "note": "evidence retrieval here is the lab's stand-in (newest k); production plans corpus queries with a model"})
    return proto


# ── rendering (reads only policy params, never the live forecast module) ──────────────────────────
def evidence_block(chosen: list[Evidence], body_chars: int) -> str:
    return "\n".join(f"[{e.id}] ({e.publish_time[:10]}, {e.source or e.kind}) {e.title}: {e.body[:body_chars]}".strip() for e in chosen)


def render_task(proto: Protocol, q: Question, chosen: list[Evidence], memory_lines: list[str] | None = None, evidence_text: str | None = None) -> str:
    """``evidence_text`` is for a policy that renders its own evidence (production research); otherwise the documents are rendered here."""
    prm = proto.policies["prompts"].params
    body = (evidence_text if evidence_text is not None else evidence_block(chosen, int(proto.policies["evidence"].params.get("body_chars", flags.BODY_CHARS)))) or prm["no_evidence"]
    end = q.closes_at[:10] or "unspecified"
    left = ""
    c, e = store.parse_time(q.cutoff), store.parse_time(q.closes_at)
    if c is not None and e is not None:
        left = f" ({max(0, (e - c).days)} days from now)"
    task = prm["task_template"].format(today=q.cutoff[:10], question=q.text, ends=end + left, rules=q.rules or "(none given)", evidence=body)
    if memory_lines and proto.policies.get("memory") and proto.policies["memory"].params.get("inject_into_prompt"):
        task += "\n\nYOUR EARLIER NOTES:\n" + "\n".join(memory_lines)
    return task
