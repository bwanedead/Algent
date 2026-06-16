"""Firecrawl — hosted page extraction (fallback behind local trafilatura)."""

from __future__ import annotations

from .base import ProviderConfig

FIRECRAWL = ProviderConfig(
    id="firecrawl",
    surfaces=("fetch_content",),
    key_env="FIRECRAWL_API_KEY",
    keyring_name="firecrawl_api_key",
)
