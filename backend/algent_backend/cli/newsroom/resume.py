"""
``newsroom resume`` — continue a run from the artifacts it already produced.

A rail writes each stage to disk as it goes. A failure late in the pipe strands finished
work rather than destroying it. Resume assesses what survived and continues from the next
unpaid stage, in the SAME run directory, so hero images and charts stay where publish
expects them and we do not re-buy research, a draft, or a figure.

Two moves, one engine:

- ``publish`` in the dry-run plan means the draft (and figures, if any) are on disk —
  the rail will skip paid editorial stages and ship.
- ``continue`` means an earlier stage is still unpaid. The rail skips whatever is present.

``--from STAGE`` forces a redo from that stage (reuse everything before it). Default is
the next missing stage. Resume never silently regenerates a missing artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .progress import (
    STAGES,
    assess,
    inject_state,
    latest_resumable,
    run_id_of,
    runs_root,
    summary,
)


def add_parser(sub: Any) -> None:
    p = sub.add_parser(
        "resume", help="continue a failed run from the artifacts it already produced")
    p.add_argument("--run", help="run directory or id prefix (default: newest resumable)")
    p.add_argument(
        "--from", dest="from_stage", choices=STAGES, default=None,
        help="redo from this stage (reuse everything before it). Default: next missing stage",
    )
    p.add_argument("--dry-run", action="store_true", help="report what it would do")
    p.set_defaults(handler=run_resume)


def _resolve_run(spec: str | None) -> Path | None:
    if spec:
        run = Path(spec)
        if run.exists():
            return run
        matches = [d for d in runs_root().glob(f"{spec}*") if d.is_dir()]
        return matches[0] if matches else run
    return latest_resumable()


def run_resume(args: Any) -> int:
    run = _resolve_run(args.run)
    if run is None:
        print(json.dumps({
            "error": "no resumable run found — every rail run is already shipped, "
                     "or none has artifacts yet",
        }, indent=2))
        return 1
    if not run.exists():
        print(json.dumps({"error": f"run not found: {run}"}, indent=2))
        return 1

    try:
        progress = assess(run, from_stage=args.from_stage)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1

    payload = summary(progress)
    if args.dry_run:
        print(json.dumps({**payload, "dry_run": True}, indent=2, ensure_ascii=False))
        return 0

    if progress.next_step == "already_done":
        print(json.dumps({**payload, "error": "already published — pass --from publish to re-ship"},
                         indent=2, ensure_ascii=False))
        return 1
    if progress.next_step == "nothing":
        print(json.dumps({**payload, "error": progress.note or "nothing resumable"},
                         indent=2, ensure_ascii=False))
        return 1
    return _continue_run(run, progress)


def _continue_run(run: Path, progress: Any) -> int:
    """Re-invoke the rail in this run directory with surviving artifacts as initial state."""
    from algent_backend.agent_system.runs.control_plane.fsio import write_json_file
    from algent_backend.agent_system.runs.control_plane.layout import RunPaths
    from algent_backend.agent_system.runs.models import RunRequest
    from algent_backend.cli.newsroom.single_flight import NewsroomBusyError, NewsroomRunLock
    from algent_backend.cli.runs.exec_run import execute

    run_id = run_id_of(run)
    paths = RunPaths(run)
    if not paths.request_file.is_file():
        print(json.dumps({
            **summary(progress),
            "error": "no request.json — this directory is not a rail run",
        }, indent=2))
        return 1

    request = RunRequest.model_validate_json(paths.request_file.read_text(encoding="utf-8"))
    # Replace artifact keys rather than merge. A prior continue wrote draft/treatment into
    # request.json; merging would resurrect them after ``--from editorial`` dropped them.
    kept = {k: v for k, v in request.input.items() if k not in ARTIFACT_STATE_KEYS}
    request = request.model_copy(update={
        "run_id": run_id,
        "input": inject_state(request.input, progress.state),
    })
    write_json_file(paths.request_file, request.model_dump())
    # Watchers poll done.json; a prior failure left one. Remove it so this continuation is live.
    if paths.done_file.exists():
        paths.done_file.unlink()

    print(json.dumps({**summary(progress), "continuing": True, "run_id": run_id},
                     indent=2, ensure_ascii=False))
    try:
        with NewsroomRunLock():
            return execute(run_id, emit_json=True)
    except NewsroomBusyError as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
