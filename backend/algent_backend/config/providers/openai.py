"""OpenAI — model provider."""

from __future__ import annotations

from .base import ProviderConfig

OPENAI = ProviderConfig(
    id="openai",
    surfaces=("model",),
    key_env="OPENAI_API_KEY",
    keyring_name="openai_api_key",
)
