"""
Smoke tests for the model resolution layer (Slice 0).

Proves a neutral ``ModelSpec`` resolves into a concrete LangChain chat model
wrapped in a ``ResolvedModel``. Offline/CI-safe: we assert correct construction
(right class, right kwargs) rather than making a live API call.
"""

from __future__ import annotations

import pytest

from algent_backend.agent_system.foundation.models import (
    ModelResolver,
    ModelSpec,
    ResolvedModel,
)


def test_resolves_anthropic_spec_to_langchain_chat_model() -> None:
    from langchain_anthropic import ChatAnthropic

    from algent_backend.agent_system.foundation.models.budget_gate import (
        BudgetGatedChatModel,
    )

    spec = ModelSpec(provider="anthropic", model="claude-sonnet-4-5", temperature=0.2)
    resolved = ModelResolver().resolve(spec)

    assert isinstance(resolved, ResolvedModel)
    assert resolved.provider == "anthropic"
    assert resolved.target == "langchain"
    assert resolved.model == "claude-sonnet-4-5"

    assert isinstance(resolved.client, BudgetGatedChatModel)
    assert isinstance(resolved.client.inner, ChatAnthropic)
    assert resolved.client.inner.model == "claude-sonnet-4-5"
    assert resolved.client.inner.temperature == 0.2
    assert resolved.client.model_id == "claude-sonnet-4-5"


def test_default_target_is_langchain(monkeypatch: pytest.MonkeyPatch) -> None:
    # ChatOpenAI builds its client (and demands a key) at construction time.
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    spec = ModelSpec(provider="openai", model="gpt-4o-mini")
    resolved = ModelResolver().resolve(spec)
    assert resolved.target == "langchain"


def test_unknown_target_raises() -> None:
    spec = ModelSpec(provider="openai", model="gpt-4o-mini")
    with pytest.raises(ValueError, match="Unknown model target"):
        ModelResolver().resolve(spec, target="native")


def test_optional_knobs_are_omitted_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset knobs should not be forced onto the client (provider defaults win)."""
    from langchain_openai import ChatOpenAI

    from algent_backend.agent_system.foundation.models.budget_gate import (
        BudgetGatedChatModel,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    spec = ModelSpec(provider="openai", model="gpt-4o-mini")
    resolved = ModelResolver().resolve(spec)

    assert isinstance(resolved.client, BudgetGatedChatModel)
    assert isinstance(resolved.client.inner, ChatOpenAI)
    assert resolved.client.inner.max_tokens is None


def test_openai_reasoning_effort_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_openai import ChatOpenAI

    from algent_backend.agent_system.foundation.models.budget_gate import (
        BudgetGatedChatModel,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    spec = ModelSpec(
        provider="openai", model="gpt-5.6-luna", temperature=0.2, reasoning_effort="low",
    )
    resolved = ModelResolver().resolve(spec)
    assert isinstance(resolved.client, BudgetGatedChatModel)
    inner = resolved.client.inner
    assert isinstance(inner, ChatOpenAI)
    model_id = getattr(inner, "model_name", None) or getattr(inner, "model", None)
    assert model_id == "gpt-5.6-luna"
    assert inner.reasoning_effort == "low"


def test_openai_spec_defaults_to_luna(monkeypatch: pytest.MonkeyPatch) -> None:
    from algent_backend.agent_system.foundation.models import openai_spec

    monkeypatch.delenv("ALGENT_OPENAI_MODEL", raising=False)
    spec = openai_spec(reasoning_effort="medium", temperature=0.3)
    assert spec.provider == "openai"
    assert spec.model == "gpt-5.6-luna"
    assert spec.reasoning_effort == "medium"
