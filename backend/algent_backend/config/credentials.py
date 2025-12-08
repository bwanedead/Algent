"""
Credential helpers (env vars first, with optional keyring fallback).
"""
from __future__ import annotations

import os
from typing import Optional

try:
    import keyring  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    keyring = None


SERVICE_NAME = "algent"

PROVIDER_KEY_MAP = {
    "openai": ("OPENAI_API_KEY", "openai_api_key"),
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    "gemini": ("GEMINI_API_KEY", "gemini_api_key"),
    "xai": ("XAI_API_KEY", "xai_api_key"),
}


def list_providers() -> list[str]:
    """Return supported provider identifiers."""
    return sorted(PROVIDER_KEY_MAP.keys())


def get_provider_api_key(provider: str) -> Optional[str]:
    """
    Return the API key for a provider.

    Order of precedence:
    1. Environment variable (e.g., OPENAI_API_KEY)
    2. Keyring entry stored under (service='algent', username='<provider>_api_key')
    """
    env_var, key_name = PROVIDER_KEY_MAP.get(provider, ("", ""))  # type: ignore[arg-type]
    if env_var and env_var in os.environ:
        return os.environ[env_var]
    if keyring and key_name:
        try:
            return keyring.get_password(SERVICE_NAME, key_name)
        except Exception:
            return None
    return None


def set_provider_api_key(provider: str, value: str) -> None:
    """Store the API key in keyring if available."""
    if not keyring:
        raise RuntimeError("keyring is not installed")
    _, key_name = PROVIDER_KEY_MAP.get(provider, ("", ""))
    if not key_name:
        raise ValueError(f"Unknown provider '{provider}'")
    keyring.set_password(SERVICE_NAME, key_name, value)
