"""Registry for cockpit project roots and adapters."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

REGISTRY_FILENAME = "registry.json"


def _registry_path() -> Path:
    return Path(__file__).resolve().parent / REGISTRY_FILENAME


def _stable_project_id(path: str) -> str:
    normalized = str(Path(path).resolve())
    base = Path(normalized).name or "project"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def _load_registry() -> Dict[str, List[dict]]:
    path = _registry_path()
    if not path.exists():
        return {"projects": [], "run_settings": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"projects": [], "run_settings": {}}
    if not isinstance(data, dict):
        return {"projects": [], "run_settings": {}}
    projects = data.get("projects")
    if not isinstance(projects, list):
        return {"projects": [], "run_settings": {}}
    run_settings = data.get("run_settings")
    if not isinstance(run_settings, dict):
        run_settings = {}
    return {"projects": projects, "run_settings": run_settings}


def _save_registry(data: Dict[str, List[dict]]) -> None:
    path = _registry_path()
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def list_projects() -> List[dict]:
    data = _load_registry()
    projects = data.get("projects", [])
    if projects:
        return projects

    default_root = Path(__file__).resolve().parents[3]
    if default_root.exists():
        project = add_project(str(default_root), name=default_root.name, adapter="ralph_engine")
        return [project]

    return projects


def get_project(project_id: str) -> Optional[dict]:
    for project in list_projects():
        if project.get("id") == project_id:
            return project
    return None


def get_run_settings(project_id: str, run_id: str) -> dict:
    data = _load_registry()
    settings = data.get("run_settings", {})
    return settings.get(project_id, {}).get(run_id, {})


def update_run_settings(project_id: str, run_id: str, updates: dict) -> dict:
    data = _load_registry()
    settings = data.setdefault("run_settings", {})
    project_settings = settings.setdefault(project_id, {})
    current = project_settings.get(run_id, {})
    if not isinstance(current, dict):
        current = {}
    current.update(updates)
    project_settings[run_id] = current
    _save_registry(data)
    return current


def add_project(path: str, name: Optional[str] = None, adapter: str = "ralph_engine") -> dict:
    project_path = str(Path(path).resolve())
    project_id = _stable_project_id(project_path)
    project_name = name or Path(project_path).name or project_id

    data = _load_registry()
    for project in data["projects"]:
        if project.get("id") == project_id or project.get("path") == project_path:
            return project

    project = {
        "id": project_id,
        "name": project_name,
        "path": project_path,
        "adapter": adapter,
    }
    data["projects"].append(project)
    _save_registry(data)
    return project
