"""
Protocol genealogy. Every protocol already names its parent (``Protocol.parent``); the policies it changed are derived from the two stored compositions, so they can
never disagree with what actually ran. ``retire`` marks a protocol abandoned (``retired/<id>.json``, write-once, with the reason): nothing else changes, so its
evidence, runs and scores stay in the store and on the boards. ``tree`` is what ``newsroom lab tree`` prints.
"""

from __future__ import annotations

from typing import Any

from . import score, store
from .contracts import Protocol


def all_protocols() -> dict[str, Protocol]:
    out = {}
    for name in store.listing("protocols"):
        raw = store.read_json(f"protocols/{name}")
        if raw:
            p = Protocol.model_validate(raw)
            out[p.id] = p
    return out


def changed(proto: Protocol, parent: Protocol | None) -> list[str]:
    """The policy versions that differ from the parent, as ``old -> new`` (``+``/``-`` when a kind was added or dropped)."""
    if parent is None:
        return []
    out = []
    for kind in sorted(set(proto.policies) | set(parent.policies)):
        new, old = proto.policies.get(kind), parent.policies.get(kind)
        if new and old and new.digest != old.digest:
            out.append(f"{old.ref} -> {new.ref}")
        elif new and not old:
            out.append(f"+ {new.ref}")
        elif old and not new:
            out.append(f"- {old.ref}")
    return out


def resolve(ref: str) -> str:
    """A protocol id from an id, a protocol name, or a prefix of an id."""
    protos = all_protocols()
    if ref in protos:
        return ref
    hits = [p.id for p in protos.values() if p.name == ref or p.id.startswith(ref)]
    if len(hits) != 1:
        raise KeyError(f"{ref!r} matches {len(hits)} protocols")
    return hits[0]


def retire(ref: str, reason: str) -> dict[str, Any]:
    pid = resolve(ref)
    if not store.exists(f"retired/{pid}.json"):
        store.write_once(f"retired/{pid}.json", {"protocol": pid, "reason": reason, "retired_at": store.now_iso()})
    return store.read_json(f"retired/{pid}.json")


def tree() -> list[dict[str, Any]]:
    """Nodes in depth-first order: id, name, depth, changed policies, runs and questions kept, and the retirement note when abandoned."""
    protos = all_protocols()
    runs: dict[str, list[str]] = {}
    for r in score.runs():
        runs.setdefault(r.protocol_id, []).append(r.question_id)
    kids: dict[str, list[str]] = {}
    for p in protos.values():
        kids.setdefault(p.parent if p.parent in protos else "", []).append(p.id)
    out: list[dict[str, Any]] = []

    def walk(pid: str, depth: int) -> None:
        p = protos[pid]
        out.append({"id": pid, "name": p.name, "depth": depth, "parent": p.parent, "changed": changed(p, protos.get(p.parent)), "runs": len(runs.get(pid, [])),
                    "questions": len(set(runs.get(pid, []))), "retired": store.read_json(f"retired/{pid}.json")})
        for c in sorted(kids.get(pid, []), key=lambda i: protos[i].name):
            walk(c, depth + 1)

    for root in sorted(kids.get("", []), key=lambda i: protos[i].name):
        walk(root, 0)
    return out


def render(nodes: list[dict[str, Any]]) -> str:
    lines = []
    for n in nodes:
        tag = f"  [ABANDONED: {n['retired']['reason']}]" if n["retired"] else ""
        lines.append(f"{'  ' * n['depth']}{'+- ' if n['depth'] else ''}{n['name']} ({n['id'][:8]})  runs {n['runs']} on {n['questions']} questions{tag}")
        lines += [f"{'  ' * n['depth']}{'|  ' if n['depth'] else '   '}changed: {c}" for c in n["changed"]]
    return "\n".join(lines)
