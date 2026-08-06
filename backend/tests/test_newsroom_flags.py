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
