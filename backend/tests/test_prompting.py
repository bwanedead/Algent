"""Tests for the shared prompt composition layer."""

from __future__ import annotations

from algent_backend.agent_system.prompting import (
    UNIVERSAL_AGENT_BASE,
    compose_system_prompt,
    stitch_message,
)


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


def test_stitch_message_joins_present_segments() -> None:
    assert stitch_message("seed", "directive") == "seed\n\ndirective"


def test_stitch_message_skips_absent_segments() -> None:
    # An optional segment can be passed as None and simply drops out.
    assert stitch_message(None, "directive") == "directive"
    assert stitch_message("seed", None, "   ") == "seed"
