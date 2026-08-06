"""Newsroom operator defaults (flags.py) — file-backed, not .env-primary."""

from __future__ import annotations

import os

import pytest

from algent_backend.agent_system.agents.newsroom import flags


@pytest.fixture(autouse=True)
def _clear_synthesis_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALGENT_SYNTHESIS", raising=False)


def test_synthesis_defaults_off_from_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flags, "SYNTHESIS_ENABLED", False)
    assert flags.synthesis_enabled() is False


def test_synthesis_file_true_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flags, "SYNTHESIS_ENABLED", True)
    assert flags.synthesis_enabled() is True


@pytest.mark.parametrize("raw,expected", [
    ("0", False),
    ("false", False),
    ("off", False),
    ("1", True),
    ("true", True),
])
def test_synthesis_env_overrides_file(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool,
) -> None:
    monkeypatch.setattr(flags, "SYNTHESIS_ENABLED", True)  # file would be on
    monkeypatch.setenv("ALGENT_SYNTHESIS", raw)
    assert flags.synthesis_enabled() is expected


def test_synthesis_target_vectors_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flags, "SYNTHESIS_TARGET_VECTORS", 40)
    assert flags.synthesis_target_vectors() == 40
    monkeypatch.setattr(flags, "SYNTHESIS_TARGET_VECTORS", 0)
    assert flags.synthesis_target_vectors() == 1


def test_t0_directive_includes_target(monkeypatch: pytest.MonkeyPatch) -> None:
    from algent_backend.agent_system.agents.discovery.synthesis import messages as syn_msg
    monkeypatch.setattr(flags, "SYNTHESIS_TARGET_VECTORS", 40)
    assert "about 40 vectors" in syn_msg._directive()
