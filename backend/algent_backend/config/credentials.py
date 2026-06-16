"""
Credential resolution — environment first, then keyring, over the provider registry.

Per-vendor key *names* live in ``config/providers/`` (grouped by vendor). This
module is the *mechanism*: given a provider id, look up its descriptor and resolve
the key from the environment (including ``.env``) or the OS keyring.

There is no longer a model-provider vs service split at the key layer — every
vendor sits in one registry. ``get_provider_api_key`` and ``get_service_api_key``
are kept as call-site-compatible aliases over the same lookup; the distinction is
now expressed by a vendor's declared surfaces, not by which map its key lives in.
"""

from __future__ import annotations

import os

from .providers import PROVIDERS, model_provider_ids

try:
    import keyring  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    keyring = None


SERVICE_NAME = "algent"


def _lookup_key(env_var: str | None, keyring_name: str | None) -> str | None:
    """Resolve a key from the environment first, then keyring."""
    if env_var and env_var in os.environ:
        return os.environ[env_var]
    if keyring and keyring_name:
        try:
            return keyring.get_password(SERVICE_NAME, keyring_name)
        except Exception:
            return None
    return None


def get_api_key(provider_id: str) -> str | None:
    """
    Return the API key for any registered vendor (model provider or service).

    Order of precedence:
    1. Environment variable (e.g., ``OPENAI_API_KEY``) — includes values from ``.env``.
    2. Keyring entry stored under (service='algent', username='<vendor>_api_key').

    Returns ``None`` for an unknown or keyless vendor.
    """
    cfg = PROVIDERS.get(provider_id)
    if cfg is None:
        return None
    return _lookup_key(cfg.key_env, cfg.keyring_name)


# Call-site-compatible aliases. Model-provider keys and external-service/tool keys
# resolve through the same registry; the two names are kept for readability at the
# call site (a model target asks for a provider key; a tool asks for a service key).
get_provider_api_key = get_api_key
get_service_api_key = get_api_key


def list_providers() -> list[str]:
    """Model providers whose keys can be set via the credentials endpoint."""
    return model_provider_ids()


def set_provider_api_key(provider_id: str, value: str) -> None:
    """Store a vendor's API key in keyring (if available)."""
    if not keyring:
        raise RuntimeError("keyring is not installed")
    cfg = PROVIDERS.get(provider_id)
    if cfg is None or not cfg.keyring_name:
        raise ValueError(f"Unknown provider '{provider_id}'")
    keyring.set_password(SERVICE_NAME, cfg.keyring_name, value)
