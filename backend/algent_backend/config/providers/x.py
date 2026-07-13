"""X (Twitter) — social/real-time search via the X API v2 (behind the web_search `x` channel)."""

from __future__ import annotations

from .base import ProviderConfig

X = ProviderConfig(
    id="x",
    surfaces=("web_search",),
    key_env="X_BEARER_TOKEN",
    keyring_name="x_bearer_token",
)
