"""File-based reader/writer for Ralph Engine run artifacts."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ralph_root(project_root: Path) -> Path:
    return project_root / "ralph"


def _runs_root(project_root: Path) -> Path:
    return _ralph_root(project_root) / "runs"


def _run_root(project_root: Path, run_id: str) -> Path:
    return _runs_root(project_root) / run_id


def _safe_read_text(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _safe_read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _event_level(event_type: str, event_data: dict) -> str:
    if event_data.get("level"):
        return str(event_data["level"]).upper()
    lowered = event_type.lower()
    if "error" in lowered or "failed" in lowered:
        return "ERROR"
    if "warn" in lowered:
        return "WARN"
    return "INFO"


def _run_state_from_json(run_json: dict, run_id: str) -> dict:
    return {
        "runId": run_id,
        "status": run_json.get("status") or "unknown",
        "phase": run_json.get("phase"),
        "iteration": run_json.get("iteration"),
        "maxIterations": run_json.get("max_iterations"),
        "createdAt": run_json.get("created_at"),
        "updatedAt": run_json.get("updated_at"),
        "startedAt": run_json.get("started_at"),
        "finishedAt": run_json.get("finished_at"),
        "error": run_json.get("error"),
        "gitBranch": run_json.get("git_branch"),
        "gitBaseBranch": run_json.get("git_base_branch"),
        "gitBaseCommit": run_json.get("git_base_commit"),
    }


def _template_run_info(run_root: Path) -> dict:
    prompt_path = run_root / "PROMPT.md"
    prd_path = run_root / "prd.json"
    is_template = prompt_path.exists() and prd_path.exists()
    return {
        "isTemplateRun": is_template,
        "hasPrompt": prompt_path.exists(),
        "hasPrd": prd_path.exists(),
    }


def list_runs(project_root: str) -> List[dict]:
    root = Path(project_root)
    runs_root = _runs_root(root)
    if not runs_root.exists():
        return []

    runs = []
    for run_dir in sorted(runs_root.iterdir()):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        run_json_path = run_dir / "run.json"
        run_json = _safe_read_json(run_json_path)
        if not run_json:
            continue

        prd = _safe_read_json(run_dir / "prd.json")
        stories = prd.get("stories", []) if isinstance(prd, dict) else []
        total_stories = len(stories)
        passed_stories = len([s for s in stories if s.get("passes")])

        run_info = {
            "id": run_id,
            "title": run_json.get("title") or prd.get("title") if isinstance(prd, dict) else None,
            **_run_state_from_json(run_json, run_id),
            "storyCounts": {
                "total": total_stories,
                "passed": passed_stories,
            },
            "artifacts": {
                "hasProgress": (run_dir / "progress.md").exists(),
                "hasSummary": (run_dir / "SUMMARY.md").exists(),
                "hasEvents": (run_dir / "events.ndjson").exists(),
                "hasControl": (run_dir / "control.json").exists(),
                "transcriptCount": len(list((run_dir / "transcripts").glob("*.md"))) if (run_dir / "transcripts").exists() else 0,
            },
            **_template_run_info(run_dir),
        }
        runs.append(run_info)
    return runs


def get_run_state(project_root: str, run_id: str) -> Optional[dict]:
    run_json = _safe_read_json(_run_root(Path(project_root), run_id) / "run.json")
    if not run_json:
        return None
    return _run_state_from_json(run_json, run_id)


def get_prd(project_root: str, run_id: str) -> Optional[dict]:
    return _safe_read_json(_run_root(Path(project_root), run_id) / "prd.json")


def get_progress_text(project_root: str, run_id: str) -> Optional[str]:
    return _safe_read_text(_run_root(Path(project_root), run_id) / "progress.md")


def get_summary_text(project_root: str, run_id: str) -> Optional[str]:
    return _safe_read_text(_run_root(Path(project_root), run_id) / "SUMMARY.md")


def get_orchestration(project_root: str, run_id: str) -> Optional[dict]:
    return _safe_read_json(_run_root(Path(project_root), run_id) / "orchestration.json")


def get_worker_result(project_root: str, run_id: str, iteration: int) -> Optional[dict]:
    run_root = _run_root(Path(project_root), run_id)
    iter_folder = _iter_folder_name(iteration)
    path = run_root / "phases" / "worker" / iter_folder / "output" / "worker_result.json"
    return _safe_read_json(path)

def get_control_signals(project_root: str, run_id: str) -> Dict[str, Any]:
    path = _run_root(Path(project_root), run_id) / "control.json"
    data = _safe_read_json(path) or {}
    return {
        "pause": bool(data.get("pause", False)),
        "stop_soft": bool(data.get("stop_soft", False)),
        "stop_hard": bool(data.get("stop_hard", False)),
        "skip_iteration": bool(data.get("skip_iteration", False)),
        "review_now": bool(data.get("review_now", False)),
        "review_next": bool(data.get("review_next", False)),
    }


def update_control_signals(project_root: str, run_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    path = _run_root(Path(project_root), run_id) / "control.json"
    current = _safe_read_json(path) or {}
    for key, value in updates.items():
        current[key] = value
    path.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    return get_control_signals(project_root, run_id)


def get_events(project_root: str, run_id: str, limit: int = 50) -> List[dict]:
    path = _run_root(Path(project_root), run_id) / "events.ndjson"
    if not path.exists():
        return []
    lines = deque(maxlen=max(limit, 1))
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            lines.append(line)

    events: List[dict] = []
    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = data.get("type", "event")
        events.append(
            {
                "timestamp": data.get("time"),
                "level": _event_level(event_type, data.get("data", {})),
                "message": data.get("message") or event_type,
                "phase": data.get("phase"),
                "iteration": data.get("iteration"),
                "type": event_type,
                "data": data.get("data", {}),
            }
        )
    return events


def get_active_phase(project_root: str, run_id: str, scan_limit: int = 500) -> Optional[dict]:
    path = _run_root(Path(project_root), run_id) / "events.ndjson"
    if not path.exists():
        return None

    lines = deque(maxlen=max(scan_limit, 1))
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            lines.append(line)

    active = {}
    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = data.get("type")
        iteration = data.get("iteration")
        phase = data.get("phase")
        if event_type == "phase_started" and iteration is not None and phase:
            active = {"iteration": iteration, "phase": phase}
        if event_type == "phase_finished" and iteration is not None and phase:
            if active.get("iteration") == iteration and active.get("phase") == phase:
                active = {}

    if not active:
        return None
    return active


def _iter_folder_name(iteration: int) -> str:
    # Iterations are 0-indexed; folder is 1-indexed.
    return f"iter-{iteration + 1:04d}"


def get_log_tail(
    project_root: str,
    run_id: str,
    phase: str,
    iteration: int,
    stream: str,
    limit: int = 200,
) -> List[str]:
    run_root = _run_root(Path(project_root), run_id)
    iter_folder = _iter_folder_name(iteration)
    log_path = (
        run_root
        / "phases"
        / phase
        / iter_folder
        / "logs"
        / f"{stream}.txt"
    )
    if not log_path.exists():
        return []

    lines = deque(maxlen=max(limit, 1))
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            lines.append(line.rstrip("\n"))
    return list(lines)


def get_live_stream(project_root: str, run_id: str, limit: int = 200) -> dict:
    active = get_active_phase(project_root, run_id)
    if not active:
        return {
            "phase": None,
            "iteration": None,
            "stdout": [],
            "stderr": [],
        }

    iteration = int(active["iteration"])
    phase = str(active["phase"])
    stdout = get_log_tail(project_root, run_id, phase, iteration, "stdout", limit)
    stderr = get_log_tail(project_root, run_id, phase, iteration, "stderr", limit)
    return {
        "phase": phase,
        "iteration": iteration,
        "stdout": stdout,
        "stderr": stderr,
    }


def get_artifacts(project_root: str, run_id: str, event_limit: int = 50) -> dict:
    return {
        "runState": get_run_state(project_root, run_id),
        "prd": get_prd(project_root, run_id),
        "progressText": get_progress_text(project_root, run_id),
        "summaryText": get_summary_text(project_root, run_id),
        "orchestration": get_orchestration(project_root, run_id),
        "controlSignals": get_control_signals(project_root, run_id),
        "events": get_events(project_root, run_id, event_limit),
    }
