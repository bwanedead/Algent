"""Helpers for reading phase outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple


def _run_root(project_root: str, run_id: str) -> Path:
    return Path(project_root) / "ralph" / "runs" / run_id


def _iter_folder_name(iteration: int) -> str:
    return f"iter-{iteration + 1:04d}"


def get_reviewer_result(project_root: str, run_id: str, iteration: int) -> Optional[dict]:
    run_root = _run_root(project_root, run_id)
    iter_folder = _iter_folder_name(iteration)
    path = run_root / "phases" / "reviewer" / iter_folder / "output" / "review_result.json"
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw, "_parse_error": True}


def list_reviewer_iterations(project_root: str, run_id: str) -> List[int]:
    run_root = _run_root(project_root, run_id)
    reviewer_root = run_root / "phases" / "reviewer"
    if not reviewer_root.exists():
        return []
    iterations: List[int] = []
    for iter_dir in reviewer_root.iterdir():
        if not iter_dir.is_dir() or not iter_dir.name.startswith("iter-"):
            continue
        output_path = iter_dir / "output" / "review_result.json"
        if not output_path.exists():
            continue
        try:
            idx = int(iter_dir.name.split("-")[1]) - 1
        except (IndexError, ValueError):
            continue
        iterations.append(idx)
    return sorted(iterations)


def get_latest_reviewer_result(project_root: str, run_id: str) -> Tuple[Optional[int], Optional[dict]]:
    run_root = _run_root(project_root, run_id)
    reviewer_root = run_root / "phases" / "reviewer"
    if not reviewer_root.exists():
        return None, None

    latest_path: Optional[Path] = None
    latest_iter: Optional[int] = None
    latest_mtime = 0.0

    for iter_dir in reviewer_root.iterdir():
        if not iter_dir.is_dir() or not iter_dir.name.startswith("iter-"):
            continue
        output_path = iter_dir / "output" / "review_result.json"
        if not output_path.exists():
            continue
        try:
            idx = int(iter_dir.name.split("-")[1]) - 1
        except (IndexError, ValueError):
            continue
        mtime = output_path.stat().st_mtime
        if mtime >= latest_mtime:
            latest_mtime = mtime
            latest_path = output_path
            latest_iter = idx

    if not latest_path:
        return None, None
    raw = latest_path.read_text(encoding="utf-8", errors="replace")
    try:
        return latest_iter, json.loads(raw)
    except json.JSONDecodeError:
        return latest_iter, {"_raw": raw, "_parse_error": True}


def list_reviewer_results(project_root: str, run_id: str) -> List[dict]:
    run_root = _run_root(project_root, run_id)
    reviewer_root = run_root / "phases" / "reviewer"
    if not reviewer_root.exists():
        return []

    results: List[dict] = []
    for iter_dir in reviewer_root.iterdir():
        if not iter_dir.is_dir() or not iter_dir.name.startswith("iter-"):
            continue
        output_path = iter_dir / "output" / "review_result.json"
        if not output_path.exists():
            continue
        try:
            idx = int(iter_dir.name.split("-")[1]) - 1
        except (IndexError, ValueError):
            continue
        raw = output_path.read_text(encoding="utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"_raw": raw, "_parse_error": True}
        results.append({"iteration": idx, "result": payload})

    results.sort(key=lambda item: item["iteration"])
    return results
