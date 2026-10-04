"""
Provider registry — all known external vendors, one module per vendor.

"Everything xAI / everything OpenAI / everything Tavily" lives in its own module
here, declaring that vendor's credential key and the surfaces it exposes. Richer
per-vendor config (endpoints, model catalogs, harness setup) joins as a vendor
grows a second surface. Keyless endpoint-only vendors (GDELT, RSS) join when
their endpoint config migrates out of the tool modules — for now they need no
credential entry.

The credential layer (``config.credentials``) resolves keys by reading these
descriptors; it never hardcodes vendor key names itself.
"""

from __future__ import annotations

from .anthropic import ANTHROPIC
from .base import ProviderConfig
from .brave import BRAVE
from .exa import EXA
from .firecrawl import FIRECRAWL
from .google import GOOGLE
from .meta import META
from .openai import OPENAI
from .tavily import TAVILY
from .x import X
from .xai import XAI

PROVIDERS: dict[str, ProviderConfig] = {
    p.id: p for p in (
        OPENAI, ANTHROPIC, GOOGLE, META, XAI, TAVILY, EXA, BRAVE, FIRECRAWL, X,
    )
}


def get_provider_config(provider_id: str) -> ProviderConfig | None:
    """Return a vendor's descriptor, or ``None`` if not registered."""
    return PROVIDERS.get(provider_id)


def model_provider_ids() -> list[str]:
    """Vendor ids that offer a model surface (settable via the credentials API)."""
    return sorted(p.id for p in PROVIDERS.values() if "model" in p.surfaces)


__all__ = ["PROVIDERS", "ProviderConfig", "get_provider_config", "model_provider_ids"]
