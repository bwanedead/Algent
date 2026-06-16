"""
Provider descriptor — per-vendor connection facts, grouped by vendor.

A ``ProviderConfig`` is *data only*: the credential env var / keyring name for a
vendor and the surfaces it offers (a model API, a search API, an external agent
harness, ...). No secrets, no logic, no LangChain. The credential layer reads
these names and resolves the actual key; mechanisms (model targets, tools,
external agents) read the surface info.

This lives in ``config/`` rather than ``agent_system/`` on purpose: provider
config is connection configuration, and the credential layer must read it
without creating an ``agent_system -> config -> agent_system`` import cycle. The
*mechanisms* that consume a provider live in ``agent_system/``; the *facts* about
how to reach a vendor live here, one module per vendor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    """Connection facts for one external vendor."""

    id: str
    #: Surfaces this vendor exposes, e.g. "model", "x_search", "grok_build",
    #: "web_search". Capability/trust live elsewhere; this is just what's offered.
    surfaces: tuple[str, ...]
    #: API-key env var, or ``None`` for a keyless vendor (e.g. GDELT, RSS).
    key_env: str | None = None
    #: Keyring username for the stored key, or ``None`` when keyless.
    keyring_name: str | None = None
