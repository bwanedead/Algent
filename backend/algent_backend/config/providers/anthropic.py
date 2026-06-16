"""Anthropic — model provider."""

from __future__ import annotations

from .base import ProviderConfig

ANTHROPIC = ProviderConfig(
    id="anthropic",
    surfaces=("model",),
    key_env="ANTHROPIC_API_KEY",
    keyring_name="anthropic_api_key",
)
