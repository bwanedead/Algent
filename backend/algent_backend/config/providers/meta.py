"""Meta Model API — OpenAI-compatible Muse Spark models."""

from __future__ import annotations

from .base import ProviderConfig

META = ProviderConfig(
    id="meta",
    surfaces=("model",),
    key_env="META_MODEL_API_KEY",
    keyring_name="meta_model_api_key",
    base_url="https://api.meta.ai/v1",
)
