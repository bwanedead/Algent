"""
Shared test fixtures.

Every test gets an isolated runs-data root so the harness control plane writes
into a temp directory, never into the repo's real ``backend/runs_data``, and the
beat rotation is held off so no test can silently start a live, minutes-long sweep.
"""

from __future__ import annotations

import pytest

from algent_backend.agent_system.runs.control_plane.layout import RUNS_DIR_ENV


@pytest.fixture(autouse=True)
def _isolated_runs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(RUNS_DIR_ENV, str(tmp_path / "runs_data"))


@pytest.fixture(autouse=True)
def _isolated_spend_budget(tmp_path, monkeypatch):
    """The spend envelope caps REAL unattended spend. A test run once claimed five run slots
    from a live overnight envelope — so no test may ever see the real file."""
    monkeypatch.setenv("ALGENT_SPEND_BUDGET", str(tmp_path / "spend_budget.json"))


@pytest.fixture(autouse=True)
def _isolated_profile_store(tmp_path, monkeypatch):
    """The profile store is the newsroom's durable research record — no test may write to it."""
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path / "profile_store"))


@pytest.fixture(autouse=True)
def _no_live_beat_sweep(monkeypatch):
    """Keep ``ensure_t0`` hermetic.

    The beats channel refreshes itself by re-sweeping the stalest slice of the beat
    registry — real DOC requests, paced at seconds apiece. That is right in production
    and wrong in a suite that promises no network, so it is off by default here. A test
    that wants the rotation drives ``beat_refresh`` directly with an injected sweep.
    """
    monkeypatch.setenv("ALGENT_BEATS_REFRESH", "0")
