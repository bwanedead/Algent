"""
Branches: isolated mutable state for one protocol. The memory namespace is a file only that branch may read or append; a fork copies it and links the
parent, so changing the fork's policies or memory can never alter the original.
"""

from __future__ import annotations

import re

from . import store
from .access import AccessDenied
from .contracts import Branch, Observation, Protocol


def _mem(branch_id: str) -> str:
    return f"branches/{branch_id}/memory.jsonl"


def load(branch_id: str) -> Branch:
    raw = store.read_json(f"branches/{branch_id}/branch.json")
    if raw is None:
        raise KeyError(f"unknown branch {branch_id}")
    return Branch.model_validate(raw)


def branch_id(name: str, protocol: Protocol) -> str:
    return f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'branch'}-{store.digest([name, protocol.id])[:6]}"


def ensure(name: str, protocol: Protocol) -> Branch:
    """The branch for (name, protocol), created on first use."""
    return load(branch_id(name, protocol)) if store.exists(f"branches/{branch_id(name, protocol)}/branch.json") else create(name, protocol)


def create(name: str, protocol: Protocol, parent: str = "", forked_memory_digest: str = "") -> Branch:
    b = Branch(id=branch_id(name, protocol), name=name, protocol_id=protocol.id, parent=parent,
               forked_memory_digest=forked_memory_digest, created_at=store.now_iso())
    store.write_once(f"branches/{b.id}/branch.json", b)
    return b


def read_memory(branch_id: str, *, caller: str) -> list[Observation]:
    if caller != branch_id:
        raise AccessDenied(f"{caller} may not read the memory of {branch_id}")
    return [Observation.model_validate(r) for r in store.read_lines(_mem(branch_id))]


def append_memory(branch_id: str, ob: Observation, *, caller: str) -> None:
    if caller != branch_id or ob.branch != branch_id:
        raise AccessDenied(f"{caller} may not write the memory of {branch_id}")
    store.append(_mem(branch_id), ob)


def memory_digest(branch_id: str) -> str:
    p = store.path(_mem(branch_id))
    return store.digest(p.read_text(encoding="utf-8")) if p.exists() else store.digest("")


def fork(parent: Branch, name: str, protocol: Protocol) -> Branch:
    """A new branch on ``protocol`` starting from a copy of the parent's memory. Notes copied across are re-stamped as the fork's own (same sources,
    method and times) so they stay readable to it and to nobody else."""
    child = create(name, protocol, parent=parent.id, forked_memory_digest=memory_digest(parent.id))
    for ob in read_memory(parent.id, caller=parent.id):
        store.append(_mem(child.id), ob.model_copy(update={"branch": child.id}))
    return child
