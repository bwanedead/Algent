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
def _isolated_pause_signal(tmp_path, monkeypatch):
    """The pause file stops the operator's live run. No test may see (or write) the real one —
    a relaunch test failed only because the operator had just paused a run."""
    from algent_backend.agent_system.foundation import pause

    monkeypatch.setattr(pause, "PAUSE_FILE", tmp_path / "newsroom_run.pause")


@pytest.fixture(autouse=True)
def _no_real_browser(monkeypatch):
    """Playwright is installed and on by default for live reads. A test must never launch a real browser
    (slow, heavy on the operator's laptop, and network-bound); tests that exercise the switch set it."""
    monkeypatch.setenv("ALGENT_FETCH_PLAYWRIGHT", "0")


@pytest.fixture(autouse=True)
def _no_live_search_backends(tmp_path, monkeypatch):
    """web_search reads our source library first and asks our own SearXNG: tests must see neither the real
    library on disk nor a live SearXNG (a laptop tunnel would answer). An empty library and an unroutable
    SearXNG make every chain start exactly where each test's fakes expect."""
    monkeypatch.setenv("ALGENT_LIBRARY_STORE", str(tmp_path / "library_iso"))
    monkeypatch.setenv("ALGENT_SEARXNG_URL", "http://127.0.0.1:9")


@pytest.fixture(autouse=True)
def _no_live_sensing_refresh(monkeypatch):
    """The daily's sensing refresh crawls the library, fetches every instrument and collects + extracts
    statements: real network and model calls. Two CLI tests built args without no_refresh and ran it for 27
    minutes. Tests that exercise refresh inject their own collectors, which this switch does not touch."""
    monkeypatch.setenv("ALGENT_SENSING_REFRESH", "0")


@pytest.fixture(autouse=True)
def _no_data_backup(monkeypatch):
    """A test must never push anything to the private data repo."""
    monkeypatch.setenv("ALGENT_DATA_BACKUP", "0")


@pytest.fixture(autouse=True)
def _isolated_pulse_store(tmp_path, monkeypatch):
    """Pulse logs are append-only institutional memory — no test may write to the real one."""
    monkeypatch.setenv("ALGENT_PULSE_STORE", str(tmp_path / "pulse_store_iso"))
    monkeypatch.setenv("ALGENT_PULSE_BACKEND", "files")     # never the live database in tests
    monkeypatch.setenv("ALGENT_INTEL_STORE", str(tmp_path / "intel_store_iso"))


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
