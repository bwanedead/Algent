"""
Shared test fixtures.

Every test gets an isolated runs-data root so the harness control plane writes
into a temp directory, never into the repo's real ``backend/runs_data``.
"""

from __future__ import annotations

import pytest

from algent_backend.agent_system.runs.control_plane.layout import RUNS_DIR_ENV


@pytest.fixture(autouse=True)
def _isolated_runs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(RUNS_DIR_ENV, str(tmp_path / "runs_data"))
