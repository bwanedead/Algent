"""
Registry for model providers.

Allows swapping OpenAI/HuggingFace/custom providers without touching loops.
"""
from __future__ import annotations

from typing import Dict, Type

from .providers import (
    AnthropicProvider,
    BaseModelProvider,
    GeminiProvider,
    OpenAIProvider,
    XAIProvider,
)


class ModelRegistry:
    """Simple in-memory registry."""

    def __init__(self, register_defaults: bool = True) -> None:
        self._providers: Dict[str, Type[BaseModelProvider]] = {}
        if register_defaults:
            self._register_builtin_providers()

    def _register_builtin_providers(self) -> None:
        self.register(OpenAIProvider.name, OpenAIProvider)
        self.register(AnthropicProvider.name, AnthropicProvider)
        self.register(GeminiProvider.name, GeminiProvider)
        self.register(XAIProvider.name, XAIProvider)

    def register(self, name: str, provider_cls: Type[BaseModelProvider]) -> None:
        self._providers[name] = provider_cls

    def create(self, name: str, **kwargs) -> BaseModelProvider:
        provider_cls = self._providers.get(name)
        if not provider_cls:
            raise ValueError(f"Provider '{name}' not registered")
        return provider_cls(**kwargs)

    def list_providers(self) -> list[str]:
        return sorted(self._providers.keys())
