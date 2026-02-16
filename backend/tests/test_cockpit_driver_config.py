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
    assert payload["driverConfig"]["source"] == "project"
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
    assert payload["driverConfig"]["source"] == "default"
    assert payload["driverConfig"]["configured"] is False


def test_run_driver_config_prefers_run_local_config(tmp_path, monkeypatch):
    project_root = tmp_path / "project-c"
    project_config_dir = project_root / "ralph"
    run_config_dir = project_root / "ralph" / "runs" / "run-1"
    project_config_dir.mkdir(parents=True)
    run_config_dir.mkdir(parents=True)

    (project_config_dir / "config.json").write_text(
        json.dumps({"driver": {"name": "claude_code"}}),
        encoding="utf-8",
    )
    (run_config_dir / "config.json").write_text(
        json.dumps({"worker_driver": "claude_code", "reviewer_driver": "codex_cli"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        http.registry,
        "get_project",
        lambda project_id: {"id": project_id, "path": str(project_root)},
    )

    status, payload, content_type = http.handle_request(
        "GET",
        "/cockpit/runs/proj-3/run-1/driver-config",
    )

    assert status == 200
    assert content_type == "application/json"
    assert payload["driverConfig"]["source"] == "run"
    assert payload["driverConfig"]["workerDriver"] == "claude_code"
    assert payload["driverConfig"]["reviewerDriver"] == "codex_cli"
    assert payload["driverConfig"]["configured"] is True


def test_run_driver_config_falls_back_to_project_config(tmp_path, monkeypatch):
    project_root = tmp_path / "project-d"
    project_config_dir = project_root / "ralph"
    project_config_dir.mkdir(parents=True)
    (project_config_dir / "config.json").write_text(
        json.dumps({"driver": {"name": "codex_cli"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        http.registry,
        "get_project",
        lambda project_id: {"id": project_id, "path": str(project_root)},
    )

    status, payload, content_type = http.handle_request(
        "GET",
        "/cockpit/runs/proj-4/run-missing/driver-config",
    )

    assert status == 200
    assert content_type == "application/json"
    assert payload["driverConfig"]["source"] == "project"
    assert payload["driverConfig"]["defaultDriver"] == "codex_cli"
    assert payload["driverConfig"]["configured"] is True
