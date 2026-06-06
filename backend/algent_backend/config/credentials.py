"""
Credential helpers (env vars first, with optional keyring fallback).

Two namespaces are kept separate on purpose: model *providers* (OpenAI, Anthropic,
...) and external *services*/tools (Tavily, ...). A tool key is not a model
provider key, so it gets its own map rather than being shoehorned into the
provider list.
"""

from __future__ import annotations

import os

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

# External services / tools (not model providers).
SERVICE_KEY_MAP = {
    "tavily": ("TAVILY_API_KEY", "tavily_api_key"),
}


def _lookup_key(env_var: str, key_name: str) -> str | None:
    """Resolve a key from the environment first, then keyring."""
    if env_var and env_var in os.environ:
        return os.environ[env_var]
    if keyring and key_name:
        try:
            return keyring.get_password(SERVICE_NAME, key_name)
        except Exception:
            return None
    return None


def list_providers() -> list[str]:
    """Return supported provider identifiers."""
    return sorted(PROVIDER_KEY_MAP.keys())


def get_provider_api_key(provider: str) -> str | None:
    """
    Return the API key for a model provider.

    Order of precedence:
    1. Environment variable (e.g., OPENAI_API_KEY)
    2. Keyring entry stored under (service='algent', username='<provider>_api_key')
    """
    env_var, key_name = PROVIDER_KEY_MAP.get(provider, ("", ""))
    return _lookup_key(env_var, key_name)


def get_service_api_key(service: str) -> str | None:
    """
    Return the API key for an external service/tool (e.g. Tavily).

    Same precedence as provider keys: environment variable first, then keyring.
    """
    env_var, key_name = SERVICE_KEY_MAP.get(service, ("", ""))
    return _lookup_key(env_var, key_name)


def set_provider_api_key(provider: str, value: str) -> None:
    """Store the API key in keyring if available."""
    if not keyring:
        raise RuntimeError("keyring is not installed")
    _, key_name = PROVIDER_KEY_MAP.get(provider, ("", ""))
    if not key_name:
        raise ValueError(f"Unknown provider '{provider}'")
    keyring.set_password(SERVICE_NAME, key_name, value)
