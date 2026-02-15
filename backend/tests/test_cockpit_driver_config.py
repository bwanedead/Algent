from __future__ import annotations

import json

from algent_backend.cockpit import http


def test_project_driver_config_reads_ralph_config(tmp_path, monkeypatch):
    project_root = tmp_path / "project-a"
    config_dir = project_root / "ralph"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "driver": {
                    "name": "claude_code",
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        http.registry,
        "get_project",
        lambda project_id: {"id": project_id, "path": str(project_root)},
    )

    status, payload, content_type = http.handle_request(
        "GET",
        "/cockpit/projects/proj-1/driver-config",
    )

    assert status == 200
    assert content_type == "application/json"
    assert payload["driverConfig"]["defaultDriver"] == "claude_code"
    assert payload["driverConfig"]["configured"] is True


def test_project_driver_config_reports_unconfigured_when_missing(tmp_path, monkeypatch):
    project_root = tmp_path / "project-b"
    project_root.mkdir(parents=True)

    monkeypatch.setattr(
        http.registry,
        "get_project",
        lambda project_id: {"id": project_id, "path": str(project_root)},
    )

    status, payload, content_type = http.handle_request(
        "GET",
        "/cockpit/projects/proj-2/driver-config",
    )

    assert status == 200
    assert content_type == "application/json"
    assert payload["driverConfig"]["defaultDriver"] is None
    assert payload["driverConfig"]["configured"] is False
