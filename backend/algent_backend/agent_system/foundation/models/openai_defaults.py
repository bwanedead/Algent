"""
Shared OpenAI defaults for explicit OpenAI stages.

``openai_spec`` always targets OpenAI (default ``gpt-5.6-luna``). Newsroom house
defaults live in ``house_defaults.house_spec`` (Meta Muse Contributor) — use that
for agent DEFAULT_MODEL values, and this module when you intentionally want OpenAI.
Override the OpenAI slug with ``ALGENT_OPENAI_MODEL``.
"""

from __future__ import annotations

import os
from typing import Any

from .specs import ModelSpec, ReasoningEffort

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
_ENV_MODEL = "ALGENT_OPENAI_MODEL"


def openai_model_id() -> str:
    return os.environ.get(_ENV_MODEL, DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL


def openai_spec(
    *,
    reasoning_effort: ReasoningEffort,
    temperature: float | None = None,
    max_tokens: int | None = None,
    streaming: bool = False,
    model: str | None = None,
    **extra: Any,
) -> ModelSpec:
    """Build an OpenAI ``ModelSpec`` (Luna unless ``ALGENT_OPENAI_MODEL`` / ``model=``)."""
    payload_extra = dict(extra)
    if streaming:
        payload_extra.setdefault("streaming", True)
        payload_extra.setdefault("stream_usage", True)
    return ModelSpec(
        provider="openai",
        model=(model.strip() if model else openai_model_id()),
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        extra=payload_extra,
    )
