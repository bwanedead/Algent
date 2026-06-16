"""Brave — independent web search index."""

from __future__ import annotations

from .base import ProviderConfig

BRAVE = ProviderConfig(
    id="brave",
    surfaces=("web_search",),
    key_env="BRAVE_API_KEY",
    keyring_name="brave_api_key",
)
