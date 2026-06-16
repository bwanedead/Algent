"""Google (Gemini) — model provider.

Canonical id is ``google`` (matches ``ModelSpec.provider``); the key env var is
``GEMINI_API_KEY``. Declaring both here is what retires the old
``google`` -> ``gemini`` aliasing the LangChain target used to carry.
"""

from __future__ import annotations

from .base import ProviderConfig

GOOGLE = ProviderConfig(
    id="google",
    surfaces=("model",),
    key_env="GEMINI_API_KEY",
    keyring_name="gemini_api_key",
)
