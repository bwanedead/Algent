"""
ModelResolver — routing.

Accepts a ``ModelSpec`` and a ``target`` name, selects the matching target
resolver, and returns a ``ResolvedModel``. Contains no LangChain imports; it only
routes. The seam here is what keeps the rail swappable — callers express *what*
model they want, the resolver decides *how* it gets built.
"""

from __future__ import annotations

from collections.abc import Iterable

from .handles import ResolvedModel
from .specs import ModelSpec
from .targets.base import ModelTarget
from .targets.langchain import LangChainTarget

#: Default target while LangChain is the only rail.
DEFAULT_TARGET = "langchain"


class ModelResolver:
    """Routes a ``ModelSpec`` to a target resolver."""

    def __init__(self, targets: Iterable[ModelTarget] | None = None) -> None:
        if targets is None:
            targets = [LangChainTarget()]
        self._targets: dict[str, ModelTarget] = {t.name: t for t in targets}

    def resolve(self, spec: ModelSpec, target: str = DEFAULT_TARGET) -> ResolvedModel:
        resolver = self._targets.get(target)
        if resolver is None:
            known = ", ".join(sorted(self._targets)) or "(none)"
            raise ValueError(f"Unknown model target '{target}'. Known targets: {known}.")
        if not resolver.can_resolve(spec):
            raise ValueError(f"Target '{target}' cannot resolve provider '{spec.provider}'.")
        return resolver.resolve(spec)
