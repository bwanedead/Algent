"""Tests for the shared prompt composition layer."""

from __future__ import annotations

from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt


def test_compose_joins_layers_in_order() -> None:
    out = compose_system_prompt("alpha", "beta", "gamma")
    assert out == "alpha\n\nbeta\n\ngamma"


def test_compose_skips_blank_layers() -> None:
    out = compose_system_prompt("alpha", "", "   ", "beta")
    assert out == "alpha\n\nbeta"


def test_compose_strips_each_layer() -> None:
    out = compose_system_prompt("  alpha  ", "\nbeta\n")
    assert out == "alpha\n\nbeta"


def test_compose_supports_arbitrary_depth() -> None:
    layers = [f"layer{i}" for i in range(6)]
    out = compose_system_prompt(*layers)
    assert out.split("\n\n") == layers


def test_universal_base_is_nonempty_text() -> None:
    assert isinstance(UNIVERSAL_AGENT_BASE, str)
    assert "Algent agent" in UNIVERSAL_AGENT_BASE
