"""Tavily — web/news search API."""

from __future__ import annotations

from .base import ProviderConfig

TAVILY = ProviderConfig(
    id="tavily",
    surfaces=("web_search",),
    key_env="TAVILY_API_KEY",
    keyring_name="tavily_api_key",
)
