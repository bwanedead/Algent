"""
RunRecorder — one object that keeps a run's control-plane surfaces in sync.

The recorder is mechanics only: it persists facts (state, events, ledger rows,
result, timeline) and never interprets them. ``RunService`` drives it; agents
reach it only through the narrow ``emit`` callable on their run context.

Event appends re-render the human timeline so ``timeline.md`` stays live.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.agent_system.artifacts import ArtifactRef
from algent_backend.agent_system.runs import events as ev
from algent_backend.agent_system.runs.models import RunRequest, RunResult

from .events_log import RunEventLog
from .fsio import atomic_write_text, write_json_file
from .layout import RunPaths, resolve_or_allocate_run_root
from .ledger import LedgerEntry, RunLedger
from .state import RunState, write_state
from .timeline import write_timeline


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RunRecorder:
    """Persists one run's lifecycle facts across all control-plane surfaces."""

    def __init__(self, run_id: str, agent_id: str, runs_root: Path | None = None) -> None:
        self.run_id = run_id
        # The run dir is <agent>/<NNNN>__<run_id>. start() allocates it; the
        # executing process finds the same one. A direct call allocates.
        self.paths: RunPaths = RunPaths(resolve_or_allocate_run_root(run_id, agent_id, runs_root))
        self._events = RunEventLog(self.paths, run_id)
        self._ledger = RunLedger(runs_root)
        self._artifact_refs: list[ArtifactRef] = []
        self._usage: dict[str, int] = {}
        self._state: RunState | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self, request: RunRequest) -> None:
        now = _now()
        self._state = RunState(
            run_id=self.run_id,
            agent_id=request.agent_id,
            runtime=request.runtime,
            status="running",
            created_at=now,
            updated_at=now,
            pid=os.getpid(),
            input=request.input,
            max_turns=request.max_turns,
            langsmith_project=os.environ.get("LANGSMITH_PROJECT")
            if os.environ.get("LANGSMITH_TRACING", "").lower() == "true"
            else None,
        )
        write_state(self.paths, self._state)
        self._ledger.append(
            LedgerEntry(
                run_id=self.run_id,
                agent_id=request.agent_id,
                runtime=request.runtime,
                status="running",
                created_at=now,
            )
        )
        self.emit(
            ev.RUN_STARTED,
            {
                "agent_id": request.agent_id,
                "runtime": request.runtime,
                "input": request.input,
                "max_turns": request.max_turns,
            },
        )

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self._events.append(event_type, payload)
        if event_type == ev.RUN_ERROR and payload and payload.get("traceback"):
            # Persist the full stack so a failure is diagnosable from disk.
            atomic_write_text(self.paths.error_file, str(payload["traceback"]))
        if event_type == ev.MODEL_USAGE and payload:
            self._usage["input_tokens"] = self._usage.get("input_tokens", 0) + int(
                payload.get("input_tokens") or 0
            )
            self._usage["output_tokens"] = self._usage.get("output_tokens", 0) + int(
                payload.get("output_tokens") or 0
            )
        write_timeline(self.paths, self._events.appended)

    def record_artifact(self, ref: ArtifactRef) -> None:
        """Hook for the ArtifactWriter: collect the ref and surface the fact."""
        self._artifact_refs.append(ref)
        self.emit(ev.ARTIFACT_WRITTEN, ref.model_dump())

    def finish(self, result: RunResult) -> None:
        now = _now()
        terminal = ev.RUN_COMPLETED if result.status == "completed" else ev.RUN_FAILED
        self.emit(
            terminal,
            {"status": result.status, "error": result.error, "output": result.output},
        )

        if self._state is not None:
            self._state = self._state.model_copy(
                update={"status": result.status, "updated_at": now, "error": result.error}
            )
            write_state(self.paths, self._state)

        write_json_file(
            self.paths.result_file,
            {
                **result.model_dump(),
                "artifacts": [ref.model_dump() for ref in self._artifact_refs],
            },
        )

        created = self._state.created_at if self._state else now
        duration = _duration_seconds(created, now)
        self._ledger.append(
            LedgerEntry(
                run_id=self.run_id,
                agent_id=result.agent_id,
                runtime=result.runtime,
                status=result.status,
                created_at=created,
                finished_at=now,
                duration_s=duration,
                input_tokens=self._usage.get("input_tokens"),
                output_tokens=self._usage.get("output_tokens"),
                artifact_count=len(self._artifact_refs),
                error=result.error,
            )
        )
        # done.json last: its existence is the terminal signal watchers poll for.
        write_json_file(self.paths.done_file, {"run_id": self.run_id, "status": result.status})


def _duration_seconds(start_iso: str, end_iso: str) -> float | None:
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
        return round((end - start).total_seconds(), 3)
    except ValueError:
        return None
