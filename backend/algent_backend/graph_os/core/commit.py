"""
Commit definitions and canonical serialization helpers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence

from .errors import CommitIntegrityError
from .ids import CommitId, WorkspaceId
from ..graphops.op_types import GraphOp, deserialize_op, serialize_op


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timestamp_to_str(value: datetime) -> str:
    utc_value = _ensure_utc(value)
    iso_value = utc_value.isoformat()
    if iso_value.endswith("+00:00"):
        return iso_value[:-6] + "Z"
    return iso_value


def _timestamp_from_str(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return _ensure_utc(parsed)


def _canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _hash_payload(payload: Dict[str, Any]) -> str:
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Commit:
    workspace_id: WorkspaceId
    commit_id: CommitId
    seq: int
    base_version: int
    actor: str
    timestamp: datetime
    ops: Sequence[GraphOp] = field(default_factory=tuple)
    prev_commit_hash: str | None = None
    commit_hash: str | None = None
    message: str | None = None
    tags: Sequence[str] = field(default_factory=tuple)

    def with_hash(self, commit_hash: str) -> "Commit":
        return replace(self, commit_hash=commit_hash)


def _commit_payload(commit: Commit, include_hash: bool) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "workspace_id": commit.workspace_id.value,
        "commit_id": commit.commit_id.value,
        "seq": commit.seq,
        "base_version": commit.base_version,
        "actor": commit.actor,
        "timestamp": _timestamp_to_str(commit.timestamp),
        "prev_commit_hash": commit.prev_commit_hash,
        "ops": [serialize_op(op) for op in commit.ops],
    }
    if commit.message:
        payload["message"] = commit.message
    if commit.tags:
        payload["tags"] = list(commit.tags)
    if include_hash:
        payload["commit_hash"] = commit.commit_hash
    return payload


def commit_to_dict(commit: Commit) -> Dict[str, Any]:
    if not commit.commit_hash:
        raise CommitIntegrityError("commit hash must be computed before serialization")
    return _commit_payload(commit, include_hash=True)


def commit_payload_for_hash(commit: Commit) -> Dict[str, Any]:
    return _commit_payload(commit, include_hash=False)


def compute_commit_hash(commit: Commit) -> str:
    payload = commit_payload_for_hash(commit)
    return _hash_payload(payload)


def serialize_commit(commit: Commit) -> Dict[str, Any]:
    return commit_to_dict(commit)


def deserialize_commit(payload: Dict[str, Any], *, verify_hash: bool = True) -> Commit:
    ops_payload = payload.get("ops", [])
    ops: List[GraphOp] = [deserialize_op(op_data) for op_data in ops_payload]
    commit = Commit(
        workspace_id=WorkspaceId.from_str(payload["workspace_id"]),
        commit_id=CommitId.from_str(payload["commit_id"]),
        seq=int(payload["seq"]),
        base_version=int(payload["base_version"]),
        actor=payload["actor"],
        timestamp=_timestamp_from_str(payload["timestamp"]),
        ops=tuple(ops),
        prev_commit_hash=payload.get("prev_commit_hash"),
        commit_hash=payload.get("commit_hash"),
        message=payload.get("message"),
        tags=tuple(payload.get("tags", [])),
    )
    if verify_hash:
        expected = compute_commit_hash(commit)
        if commit.commit_hash != expected:
            raise CommitIntegrityError(
                f"commit {commit.commit_id.value} has invalid hash"
            )
    return commit


def build_commit(
    *,
    workspace_id: WorkspaceId,
    seq: int,
    base_version: int,
    actor: str,
    ops: Iterable[GraphOp],
    timestamp: datetime,
    prev_commit_hash: str | None,
    commit_id: CommitId | None = None,
    message: str | None = None,
    tags: Sequence[str] | None = None,
) -> Commit:
    commit = Commit(
        workspace_id=workspace_id,
        commit_id=commit_id or CommitId.new(),
        seq=seq,
        base_version=base_version,
        actor=actor,
        timestamp=_ensure_utc(timestamp),
        ops=tuple(ops),
        prev_commit_hash=prev_commit_hash,
        message=message,
        tags=tuple(tags or ()),
    )
    commit_hash = compute_commit_hash(commit)
    return commit.with_hash(commit_hash)
