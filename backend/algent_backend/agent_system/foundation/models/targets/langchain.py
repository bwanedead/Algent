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

OpenAI and Meta (OpenAI-compatible) share ``ChatOpenAI``; Meta adds ``base_url``.
Anthropic/Google keep their own wrappers. Common knobs (``model``, ``api_key``,
``temperature``, ``max_tokens``, ``timeout``, ``max_retries``) are shared.
"""

from __future__ import annotations

import os
from typing import Any

from algent_backend.config import get_provider_api_key, get_provider_config

from ..handles import ResolvedModel
from ..specs import ModelSpec
from .base import ModelTarget

TARGET_NAME = "langchain"

# Providers this target knows how to build (i.e. has an installed langchain-*
# integration for). This is target capability, not provider config: a vendor can
# be a model provider in the registry without this target supporting it yet.
_SUPPORTED = {"openai", "anthropic", "google", "meta"}
_OPENAI_COMPAT = frozenset({"openai", "meta"})
_ENV_META_BASE = "META_MODEL_API_BASE_URL"


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
        if provider in _OPENAI_COMPAT:
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

        if spec.provider == "meta":
            cfg = get_provider_config("meta")
            base = (os.environ.get(_ENV_META_BASE) or "").strip() or (
                (cfg.base_url if cfg else None) or ""
            )
            if not base:
                raise ValueError(
                    "Meta provider has no base_url; set META_MODEL_API_BASE_URL "
                    "or ProviderConfig.base_url on meta."
                )
            kwargs["base_url"] = base.rstrip("/")

        for field in ("temperature", "max_tokens", "timeout", "max_retries"):
            value = getattr(spec, field)
            if value is not None:
                kwargs[field] = value

        # OpenAI GPT-5.x and Meta Muse: pass reasoning when set. Function tools +
        # reasoning need the Responses API on OpenAI; Meta also exposes Responses
        # as the full agentic surface — use it whenever effort is set.
        if spec.provider in _OPENAI_COMPAT and spec.reasoning_effort is not None:
            kwargs["reasoning_effort"] = spec.reasoning_effort
            if spec.reasoning_effort != "none":
                kwargs.setdefault("use_responses_api", True)

        # Provider-specific escape hatch wins over nothing else; it is last.
        kwargs.update(spec.extra)

        # ChatOpenAI with streaming=True puts stream=true into Responses ``create``
        # even on the non-stream ``_generate`` path used by ReAct ``invoke``. The
        # SDK then returns a Stream object and construction crashes. Prefer correct
        # tool+reasoning calls over token streaming for these models.
        #
        # OpenAI Luna also needs previous_response_id + truncation to avoid
        # replaying full reasoning blocks every ReAct turn. Meta's 1M context does
        # not need that chain — leave those OpenAI-only.
        if kwargs.get("use_responses_api") and kwargs.get("reasoning_effort") not in (
            None,
            "none",
        ):
            kwargs["streaming"] = False
            kwargs.pop("stream_usage", None)
            if spec.provider == "openai":
                kwargs.setdefault("use_previous_response_id", True)
                kwargs.setdefault("truncation", "auto")

        return kwargs
