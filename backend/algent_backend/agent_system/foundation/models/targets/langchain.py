"""
LangChain model target.

This is the ONLY module in the codebase allowed to import LangChain model
wrappers. Agents and runtimes never import them directly — they ask the resolver
for a model and receive a ``ResolvedModel`` whose ``client`` is the LangChain
chat model.

Strategy: explicit provider -> wrapper-class mapping. It keeps the mapping
obvious while we learn the LangChain surface. LangChain's ``init_chat_model(...)``
one-liner could collapse this later; switching is fully internal to this file
and changes neither ``ModelSpec`` nor callers.

The three providers share kwarg names on their constructors (``model``,
``api_key``, ``temperature``, ``max_tokens``, ``timeout``, ``max_retries``);
Google aliases ``max_tokens`` to ``max_output_tokens`` internally. So one common
kwargs dict serves all three — no per-provider translation needed.
"""

from __future__ import annotations

from typing import Any

from algent_backend.config import get_provider_api_key

from ..handles import ResolvedModel
from ..specs import ModelSpec
from .base import ModelTarget

TARGET_NAME = "langchain"

# Providers this target knows how to build (i.e. has an installed langchain-*
# integration for). This is target capability, not provider config: a vendor can
# be a model provider in the registry without this target supporting it yet.
_SUPPORTED = {"openai", "anthropic", "google"}


class LangChainTarget(ModelTarget):
    """Builds LangChain chat models from a ``ModelSpec``."""

    name = TARGET_NAME

    def can_resolve(self, spec: ModelSpec) -> bool:
        return spec.provider in _SUPPORTED

    def resolve(self, spec: ModelSpec) -> ResolvedModel:
        chat_cls = self._chat_class(spec.provider)
        client = chat_cls(**self._build_kwargs(spec))
        from algent_backend.agent_system.foundation.models.budget_gate import (
            gate_chat_model,
        )

        # Every resolved LangChain client is budget-gated so structured one-shots
        # (review/headline/caveat) and ReAct turns share one authorization seam.
        client = gate_chat_model(
            client,
            model_id=spec.model,
            max_output_tokens=spec.max_tokens,
        )
        return ResolvedModel(
            provider=spec.provider,
            target=self.name,
            model=spec.model,
            client=client,
        )

    def _chat_class(self, provider: str) -> type:
        """Lazily import and return the LangChain chat-model class for a provider."""
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic
        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI
        raise ValueError(f"LangChain target does not support provider '{provider}'.")

    def _build_kwargs(self, spec: ModelSpec) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": spec.model}

        api_key = get_provider_api_key(spec.provider)
        if api_key:
            kwargs["api_key"] = api_key

        for field in ("temperature", "max_tokens", "timeout", "max_retries"):
            value = getattr(spec, field)
            if value is not None:
                kwargs[field] = value

        # OpenAI GPT-5.x: omit → API defaults to medium reasoning. Pass through
        # only when set so Anthropic/Google specs stay untouched.
        if spec.provider == "openai" and spec.reasoning_effort is not None:
            kwargs["reasoning_effort"] = spec.reasoning_effort

        # Provider-specific escape hatch wins over nothing else; it is last.
        kwargs.update(spec.extra)
        return kwargs
