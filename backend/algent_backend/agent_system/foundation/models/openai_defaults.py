"""
Shared OpenAI defaults for newsroom / agent stages.

One house model (``gpt-5.6-luna``) across OpenAI stages; stages differ by
``reasoning_effort`` (low vs medium), not by model slug. Override the slug with
``ALGENT_OPENAI_MODEL`` when testing another OpenAI id without editing every spec.
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
    """Build an OpenAI ``ModelSpec`` on the house default (Luna unless overridden)."""
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
