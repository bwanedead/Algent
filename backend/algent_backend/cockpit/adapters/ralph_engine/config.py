"""Read Ralph Engine project-level configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _config_path(project_root: Path) -> Path:
    return project_root / "ralph" / "config.json"


def _safe_read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def get_driver_config(project_root: str) -> dict:
    """Return default driver info from ``ralph/config.json`` when available."""
    project_path = Path(project_root)
    config_path = _config_path(project_path)
    config = _safe_read_json(config_path)
    driver_name = None

    if isinstance(config, dict):
        driver = config.get("driver")
        if isinstance(driver, dict):
            candidate = driver.get("name")
            if isinstance(candidate, str) and candidate.strip():
                driver_name = candidate.strip()

    return {
        "configPath": str(config_path),
        "defaultDriver": driver_name,
        "configured": driver_name is not None,
    }
