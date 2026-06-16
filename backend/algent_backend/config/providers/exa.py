"""Exa — semantic/neural search API."""

from __future__ import annotations

from .base import ProviderConfig

EXA = ProviderConfig(
    id="exa",
    surfaces=("semantic_search",),
    key_env="EXA_API_KEY",
    keyring_name="exa_api_key",
)
