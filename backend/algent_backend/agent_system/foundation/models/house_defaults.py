"""
House model defaults — the newsroom's main-tier ModelSpec.

Default is Meta Muse Spark 1.2 Contributor (``muse-spark-1.2-contributor``) via the
OpenAI-compatible Meta Model API. Newsroom workloads are public-source material and
fit the Contributor data terms; do not point confidential/internal jobs here.

Swap / kill controls (no redeploy needed):
- ``ALGENT_META_ENABLED=0`` — fall back to OpenAI Luna for every ``house_spec``
- ``ALGENT_HOUSE_PROVIDER`` / ``ALGENT_HOUSE_MODEL`` — override provider or model id
- ``openai_spec(...)`` / ``ALGENT_OPENAI_MODEL`` — explicit OpenAI path (Luna kept)

Pricing for Contributor is cheap because Meta may train on prompts/completions.
Standard Muse Spark ids stay available via ``ALGENT_HOUSE_MODEL=muse-spark-1.2``.
"""

from __future__ import annotations

import os
from typing import Any

from .openai_defaults import openai_spec
from .specs import ModelSpec, Provider, ReasoningEffort

DEFAULT_HOUSE_PROVIDER: Provider = "meta"
DEFAULT_HOUSE_MODEL = "muse-spark-1.2-contributor"

_ENV_PROVIDER = "ALGENT_HOUSE_PROVIDER"
_ENV_MODEL = "ALGENT_HOUSE_MODEL"
_ENV_META_ENABLED = "ALGENT_META_ENABLED"


def meta_enabled() -> bool:
    """Kill switch: any of 0/false/no/off disables Meta for house defaults."""
    return os.environ.get(_ENV_META_ENABLED, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def house_provider() -> Provider:
    if not meta_enabled():
        return "openai"
    raw = (os.environ.get(_ENV_PROVIDER) or DEFAULT_HOUSE_PROVIDER).strip().lower()
    # House catalog today is Meta Muse or OpenAI Luna — other providers need their own model ids.
    if raw in ("meta", "openai"):
        return raw  # type: ignore[return-value]
    return DEFAULT_HOUSE_PROVIDER


def house_model_id() -> str:
    if house_provider() == "openai":
        from .openai_defaults import openai_model_id
        return openai_model_id()
    return (os.environ.get(_ENV_MODEL) or DEFAULT_HOUSE_MODEL).strip() or DEFAULT_HOUSE_MODEL


def house_spec(
    *,
    reasoning_effort: ReasoningEffort,
    temperature: float | None = None,
    max_tokens: int | None = None,
    streaming: bool = False,
    model: str | None = None,
    **extra: Any,
) -> ModelSpec:
    """Build the house ``ModelSpec`` (Meta Muse Contributor unless swapped)."""
    provider = house_provider()
    if provider == "openai":
        return openai_spec(
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=streaming,
            model=model,
            **extra,
        )

    payload_extra = dict(extra)
    if streaming:
        payload_extra.setdefault("streaming", True)
        payload_extra.setdefault("stream_usage", True)
    return ModelSpec(
        provider=provider,
        model=(model.strip() if model else house_model_id()),
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        extra=payload_extra,
    )
