"""
ModelSpec — Algent's neutral request for a model.

This is the contract a caller uses to say *what* model it wants, independent of
*how* it gets built. It carries only the model identity plus common generation /
transport knobs; provider-specific oddities go in ``extra`` so they don't
pollute the main contract.

Deliberately co-located with the model layer rather than a central
``definitions/`` package: spinning one up to hold a single contract would be
premature. When ``AgentSpec`` arrives and references ``ModelSpec``, we'll decide
intentionally whether contracts consolidate or stay co-located per domain.

Note: ``target`` (which rail builds the model) is *not* a field here. That is a
runtime concern — rail is a per-agent property — so it is passed to the resolver
instead. See ``resolver.ModelResolver.resolve``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Provider = Literal["openai", "anthropic", "google", "meta"]
ReasoningEffort = Literal["low", "medium", "high"]


class ModelSpec(BaseModel):
    """Neutral description of a requested model."""

    provider: Provider
    model: str

    temperature: float | None = None
    max_tokens: int | None = None
    timeout: float | None = None
    max_retries: int | None = None
    # GPT-5.x defaults to medium effort when omitted — always set intentionally
    # on OpenAI stages so triage stays cheap and heavy stages stay deliberate.
    reasoning_effort: ReasoningEffort | None = None

    extra: dict[str, Any] = Field(default_factory=dict)
