"""xAI — model provider, plus the Grok X-search API and the Grok Build harness.

One vendor, several surfaces: the same ``XAI_API_KEY`` powers Grok as a model,
the Grok-mediated X search (``xai_x_search``), and (later) the Grok Build
external-agent harness. This is the canonical example of why config is grouped
by vendor: all of xAI's surfaces share one credential and live in one place.
"""

from __future__ import annotations

from .base import ProviderConfig

XAI = ProviderConfig(
    id="xai",
    surfaces=("model", "x_search", "grok_build"),
    key_env="XAI_API_KEY",
    keyring_name="xai_api_key",
)
