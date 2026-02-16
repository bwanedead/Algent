"""HTTP routing for cockpit endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from algent_backend.cockpit import registry
from algent_backend.cockpit.adapters.ralph_engine import config as ralph_config
from algent_backend.cockpit.adapters.ralph_engine import doctor as ralph_doctor
from algent_backend.cockpit.adapters.ralph_engine import outputs as ralph_outputs
from algent_backend.cockpit.adapters.ralph_engine import reader as ralph_reader
from algent_backend.cockpit.adapters.ralph_engine import runner as ralph_runner


Response = Tuple[int, Any, str]


def _json_response(status: int, payload: Any) -> Response:
    return status, payload, "application/json"


def _text_response(status: int, payload: str) -> Response:
    return status, payload, "text/plain"


def _error(status: int, message: str) -> Response:
    return _json_response(status, {"status": "error", "message": message})


def _parse_path(path: str) -> Tuple[str, Dict[str, list]]:
    parsed = urlparse(path)
    return parsed.path.rstrip("/"), parse_qs(parsed.query)


def _get_project_or_error(project_id: str) -> Optional[dict]:
    return registry.get_project(project_id)


def _adapter_reader(project: dict):
    adapter = project.get("adapter") or "ralph_engine"
    if adapter == "ralph_engine":
        return ralph_reader
    return None


def handle_request(method: str, path: str, payload: Optional[dict] = None) -> Optional[Response]:
    route, query = _parse_path(path)

    if not route.startswith("/cockpit"):
        return None

    if method == "GET" and route == "/cockpit/projects":
        return _json_response(200, {"projects": registry.list_projects()})

    if method == "POST" and route == "/cockpit/projects":
        payload = payload or {}
        project_path = payload.get("path")
        name = payload.get("name")
        adapter = payload.get("adapter", "ralph_engine")
        if not project_path:
            return _error(400, "path is required")
        if not Path(project_path).exists():
            return _error(400, "path does not exist")
        project = registry.add_project(project_path, name=name, adapter=adapter)
        return _json_response(200, {"project": project})

    if method == "GET" and route.startswith("/cockpit/run-settings/"):
        parts = route.split("/")
        if len(parts) == 5:
            project_id = parts[3]
            run_id = parts[4]
            settings = registry.get_run_settings(project_id, run_id)
            return _json_response(200, {"settings": settings})

    if method == "PATCH" and route.startswith("/cockpit/run-settings/"):
        parts = route.split("/")
        if len(parts) == 5:
            project_id = parts[3]
            run_id = parts[4]
            updates = payload or {}
            settings = registry.update_run_settings(project_id, run_id, updates)
            return _json_response(200, {"settings": settings})

    if method == "GET" and route.startswith("/cockpit/projects/"):
        parts = route.split("/")
        if len(parts) == 4 and parts[3]:
            project_id = parts[3]
            project = _get_project_or_error(project_id)
            if not project:
                return _error(404, "project not found")
            return _json_response(200, {"project": project})
        if len(parts) == 5 and parts[4] == "driver-config":
            project_id = parts[3]
            project = _get_project_or_error(project_id)
            if not project:
                return _error(404, "project not found")
            config = ralph_config.get_project_driver_config(project["path"])
            return _json_response(200, {"driverConfig": config})
        if len(parts) == 5 and parts[4] == "runs":
            project_id = parts[3]
            project = _get_project_or_error(project_id)
            if not project:
                return _error(404, "project not found")
            adapter = _adapter_reader(project)
            if adapter is None:
                return _error(400, "unknown adapter")
            runs = adapter.list_runs(project["path"])
            return _json_response(200, {"runs": runs})

    if route.startswith("/cockpit/runs/"):
        parts = route.split("/")
        if len(parts) < 5:
            return _error(400, "run route requires project and run id")
        project_id = parts[3]
        run_id = parts[4]
        project = _get_project_or_error(project_id)
        if not project:
            return _error(404, "project not found")
        adapter = _adapter_reader(project)
        if adapter is None:
            return _error(400, "unknown adapter")

        if len(parts) == 5 and method == "GET":
            run_state = adapter.get_run_state(project["path"], run_id)
            if not run_state:
                return _error(404, "run not found")
            return _json_response(200, {"run": run_state})

        if len(parts) == 6:
            resource = parts[5]
            if method == "GET" and resource == "prd":
                prd = adapter.get_prd(project["path"], run_id)
                return _json_response(200, {"prd": prd})
            if method == "GET" and resource == "driver-config":
                config = ralph_config.get_run_driver_config(project["path"], run_id)
                return _json_response(200, {"driverConfig": config})
            if method == "GET" and resource == "progress":
                text = adapter.get_progress_text(project["path"], run_id) or ""
                return _text_response(200, text)
            if method == "GET" and resource == "summary":
                text = adapter.get_summary_text(project["path"], run_id) or ""
                return _text_response(200, text)
            if method == "GET" and resource == "events":
                limit_param = query.get("limit", ["50"])[0]
                try:
                    limit = int(limit_param)
                except ValueError:
                    limit = 50
                events = adapter.get_events(project["path"], run_id, limit)
                return _json_response(200, {"events": events})
            if method == "GET" and resource == "orchestration":
                orchestration = adapter.get_orchestration(project["path"], run_id)
                return _json_response(200, {"orchestration": orchestration})
            if method == "PATCH" and resource == "orchestration":
                updates = payload or {}
                orchestration = adapter.update_orchestration(project["path"], run_id, updates)
                return _json_response(200, {"orchestration": orchestration})
            if method == "GET" and resource == "reviewer-result":
                iteration_param = query.get("iteration", [None])[0]
                if iteration_param is None:
                    return _error(400, "iteration is required")
                try:
                    iteration = int(iteration_param)
                except ValueError:
                    return _error(400, "iteration must be an integer")
                result = ralph_outputs.get_reviewer_result(project["path"], run_id, iteration)
                return _json_response(200, {"result": result})
            if method == "GET" and resource == "reviewer-iterations":
                iterations = ralph_outputs.list_reviewer_iterations(project["path"], run_id)
                return _json_response(200, {"iterations": iterations})
            if method == "GET" and resource == "reviewer-latest":
                iteration, result = ralph_outputs.get_latest_reviewer_result(project["path"], run_id)
                return _json_response(200, {"iteration": iteration, "result": result})
            if method == "GET" and resource == "reviewer-results":
                results = ralph_outputs.list_reviewer_results(project["path"], run_id)
                return _json_response(200, {"results": results})
            if method == "POST" and resource == "execute":
                payload = payload or {}
                command = payload.get("command")
                title = payload.get("title", "Ralph Command")
                cwd = payload.get("cwd")
                result = ralph_runner.run_in_terminal(command, title, cwd=cwd)
                status = 200 if result.get("status") == "ok" else 500
                return _json_response(status, {"result": result})
            if method == "GET" and resource == "live":
                limit_param = query.get("limit", ["200"])[0]
                try:
                    limit = int(limit_param)
                except ValueError:
                    limit = 200
                live = adapter.get_live_stream(project["path"], run_id, limit)
                return _json_response(200, {"live": live})
            if method == "GET" and resource == "live-feed":
                lines = adapter.get_full_stdout_feed(project["path"], run_id)
                return _json_response(200, {"lines": lines})
            if method == "GET" and resource == "logs":
                phase = query.get("phase", [None])[0]
                iteration_param = query.get("iteration", [None])[0]
                stream = query.get("stream", ["stdout"])[0]
                limit_param = query.get("limit", ["200"])[0]
                if not phase or iteration_param is None:
                    return _error(400, "phase and iteration are required")
                try:
                    iteration = int(iteration_param)
                except ValueError:
                    return _error(400, "iteration must be an integer")
                try:
                    limit = int(limit_param)
                except ValueError:
                    limit = 200
                lines = adapter.get_log_tail(project["path"], run_id, phase, iteration, stream, limit)
                return _json_response(
                    200,
                    {"phase": phase, "iteration": iteration, "stream": stream, "lines": lines},
                )
            if method == "GET" and resource == "control":
                control = adapter.get_control_signals(project["path"], run_id)
                return _json_response(200, {"control": control})
            if method == "PATCH" and resource == "control":
                updates = payload or {}
                control = adapter.update_control_signals(project["path"], run_id, updates)
                return _json_response(200, {"control": control})
            if method == "GET" and resource == "artifacts":
                limit_param = query.get("limit", ["50"])[0]
                try:
                    limit = int(limit_param)
                except ValueError:
                    limit = 50
                artifacts = adapter.get_artifacts(project["path"], run_id, limit)
                return _json_response(200, {"artifacts": artifacts})
            if method == "POST" and resource == "doctor":
                result = ralph_doctor.run_doctor(project["path"], run_id)
                return _json_response(200, {"doctor": result})

    return _error(404, f"Unknown cockpit route: {route}")
