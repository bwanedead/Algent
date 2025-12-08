"""
Registry for model providers.

Allows swapping OpenAI/HuggingFace/custom providers without touching loops.
"""
from __future__ import annotations

from typing import Dict, Type

from .providers.base_provider import BaseModelProvider


class ModelRegistry:
    """Simple in-memory registry."""

    def __init__(self) -> None:
        self._providers: Dict[str, Type[BaseModelProvider]] = {}

    def register(self, name: str, provider_cls: Type[BaseModelProvider]) -> None:
        self._providers[name] = provider_cls

    def create(self, name: str, **kwargs) -> BaseModelProvider:
        provider_cls = self._providers.get(name)
        if not provider_cls:
            raise ValueError(f"Provider '{name}' not registered")
        return provider_cls(**kwargs)
