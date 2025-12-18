"""
Commit-as-file workspace store.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List

from ...core.commit import Commit, deserialize_commit, serialize_commit
from ...core.errors import CommitIntegrityError
from ...core.ids import WorkspaceId
from ...core.primitives.snapshot import Snapshot
from ...graphops.op_apply import apply_ops
from ...graphops.op_types import GraphOp
from ..store_interface import WorkspaceLedgerState, WorkspaceStore
from .lock import WorkspaceFileLock


class CommitLedgerStore(WorkspaceStore):
    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path
        self.root_path.mkdir(parents=True, exist_ok=True)

    def _normalize_workspace_id(self, workspace_id: str | WorkspaceId) -> WorkspaceId:
        if isinstance(workspace_id, WorkspaceId):
            return workspace_id
        return WorkspaceId.from_str(workspace_id)

    def _workspace_dir(self, workspace_id: WorkspaceId) -> Path:
        return self.root_path / "workspaces" / workspace_id.value

    def _commits_dir(self, workspace_id: WorkspaceId) -> Path:
        return self._workspace_dir(workspace_id) / "commits"

    def _lock_path(self, workspace_id: WorkspaceId) -> Path:
        return self._workspace_dir(workspace_id) / ".lock"

    def workspace_lock(self, workspace_id: str) -> WorkspaceFileLock:
        workspace = self._normalize_workspace_id(workspace_id)
        lock_path = self._lock_path(workspace)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        return WorkspaceFileLock(lock_path)

    def load_state(self, workspace_id: str) -> WorkspaceLedgerState:
        workspace = self._normalize_workspace_id(workspace_id)
        commits_dir = self._commits_dir(workspace)
        commits_dir.mkdir(parents=True, exist_ok=True)
        snapshot = Snapshot.empty(workspace)
        head_hash: str | None = None
        seen_op_ids: set[str] = set()
        next_seq = 1
        commit_paths = sorted(
            path
            for path in commits_dir.iterdir()
            if path.is_file() and self._is_commit_file(path.name)
        )
        for path in commit_paths:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            commit = deserialize_commit(payload)
            if commit.workspace_id.value != workspace.value:
                raise CommitIntegrityError(
                    f"commit at {path} references workspace {commit.workspace_id.value}"
                )
            expected_seq = self._seq_from_filename(path.name)
            if commit.seq != expected_seq or commit.seq != next_seq:
                raise CommitIntegrityError(
                    f"commit sequence mismatch at {path}, expected {next_seq}"
                )
            if commit.prev_commit_hash != head_hash:
                raise CommitIntegrityError(
                    f"hash chain mismatch at commit {commit.seq:08d}"
                )
            snapshot = apply_ops(snapshot, commit.ops)
            head_hash = commit.commit_hash
            next_seq += 1
            self._index_ops(commit.ops, seen_op_ids)
        return WorkspaceLedgerState(
            workspace_id=workspace,
            snapshot=snapshot,
            next_seq=next_seq,
            head_hash=head_hash,
            seen_op_ids=seen_op_ids,
        )

    def append_commit(self, commit: Commit) -> None:
        workspace = self._normalize_workspace_id(commit.workspace_id)
        commits_dir = self._commits_dir(workspace)
        commits_dir.mkdir(parents=True, exist_ok=True)
        filename = self._commit_filename(commit.seq)
        final_path = commits_dir / filename
        if final_path.exists():
            raise CommitIntegrityError(
                f"commit file {filename} already exists for workspace {workspace.value}"
            )
        expected_prev = self._read_head_hash(commits_dir)
        if commit.seq != self._expected_next_seq(commits_dir):
            raise CommitIntegrityError("commit sequence out of order")
        if commit.prev_commit_hash != expected_prev:
            raise CommitIntegrityError("prev hash mismatch during append")
        payload = serialize_commit(commit)
        tmp_path = commits_dir / f".tmp_{commit.commit_id.value}.json"
        self._write_atomic(tmp_path, final_path, payload)

    def _write_atomic(self, tmp_path: Path, final_path: Path, payload: dict) -> None:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, final_path)
            self._fsync_directory(final_path.parent)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    @staticmethod
    def _is_commit_file(name: str) -> bool:
        return name.endswith(".json") and name[:-5].isdigit()

    @staticmethod
    def _commit_filename(seq: int) -> str:
        return f"{seq:08d}.json"

    @staticmethod
    def _seq_from_filename(name: str) -> int:
        return int(name[:-5])

    @staticmethod
    def _index_ops(ops: Iterable[GraphOp], seen: set[str]) -> None:
        for op in ops:
            op_id = op.op_id.value
            if op_id in seen:
                raise CommitIntegrityError(f"duplicate op id {op_id} in ledger")
            seen.add(op_id)

    @staticmethod
    def _expected_next_seq(commits_dir: Path) -> int:
        seq = 1
        for path in sorted(
            p for p in commits_dir.iterdir() if p.is_file() and CommitLedgerStore._is_commit_file(p.name)
        ):
            seq = CommitLedgerStore._seq_from_filename(path.name) + 1
        return seq

    @staticmethod
    def _read_head_hash(commits_dir: Path) -> str | None:
        commit_paths = sorted(
            p for p in commits_dir.iterdir() if p.is_file() and CommitLedgerStore._is_commit_file(p.name)
        )
        if not commit_paths:
            return None
        last_path = commit_paths[-1]
        with last_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload.get("commit_hash")

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            fd = os.open(directory, os.O_RDONLY)
        except (FileNotFoundError, NotADirectoryError, OSError):
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)
