"""Read Ralph Engine run/project configuration relevant to cockpit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _config_path(project_root: Path) -> Path:
    return project_root / "ralph" / "config.json"


def _run_config_path(project_root: Path, run_id: str) -> Path:
    return project_root / "ralph" / "runs" / run_id / "config.json"


def _safe_read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _extract_driver_fields(config: Optional[dict]) -> dict:
    if not isinstance(config, dict):
        return {
            "defaultDriver": None,
            "workerDriver": None,
            "reviewerDriver": None,
        }

    driver_name = None
    worker_driver = config.get("worker_driver")
    reviewer_driver = config.get("reviewer_driver")

    driver = config.get("driver")
    if isinstance(driver, dict):
        candidate = driver.get("name")
        if isinstance(candidate, str) and candidate.strip():
            driver_name = candidate.strip()

    return {
        "defaultDriver": driver_name,
        "workerDriver": worker_driver if isinstance(worker_driver, str) and worker_driver.strip() else None,
        "reviewerDriver": reviewer_driver if isinstance(reviewer_driver, str) and reviewer_driver.strip() else None,
    }


def _is_configured(fields: dict) -> bool:
    return any(
        [
            fields.get("defaultDriver") is not None,
            fields.get("workerDriver") is not None,
            fields.get("reviewerDriver") is not None,
        ]
    )


def get_project_driver_config(project_root: str) -> dict:
    project_path = Path(project_root)
    config_path = _config_path(project_path)
    fields = _extract_driver_fields(_safe_read_json(config_path))
    configured = _is_configured(fields)
    return {
        "configPath": str(config_path),
        "source": "project" if configured else "default",
        **fields,
        "configured": configured,
    }


def get_run_driver_config(project_root: str, run_id: str) -> dict:
    project_path = Path(project_root)
    run_config_path = _run_config_path(project_path, run_id)
    project_config_path = _config_path(project_path)

    run_fields = _extract_driver_fields(_safe_read_json(run_config_path))
    if _is_configured(run_fields):
        return {
            "configPath": str(run_config_path),
            "runConfigPath": str(run_config_path),
            "projectConfigPath": str(project_config_path),
            "source": "run",
            **run_fields,
            "configured": True,
        }

    project_fields = _extract_driver_fields(_safe_read_json(project_config_path))
    project_configured = _is_configured(project_fields)
    return {
        "configPath": str(project_config_path),
        "runConfigPath": str(run_config_path),
        "projectConfigPath": str(project_config_path),
        "source": "project" if project_configured else "default",
        **project_fields,
        "configured": project_configured,
    }


def get_driver_config(project_root: str) -> dict:
    """Backward-compatible alias for older cockpit callers."""
    return get_project_driver_config(project_root)
