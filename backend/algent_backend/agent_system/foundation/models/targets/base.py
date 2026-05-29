"""
Target resolver interface.

Defining the protocol up front is what makes adding a future ``native`` target
additive rather than a refactor: the resolver only ever talks to this surface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..handles import ResolvedModel
from ..specs import ModelSpec


class ModelTarget(ABC):
    """One implementation path for building a model from a ``ModelSpec``."""

    #: Stable identifier used by the resolver to select this target.
    name: str

    @abstractmethod
    def can_resolve(self, spec: ModelSpec) -> bool:
        """Return True if this target can build a model for ``spec``."""

    @abstractmethod
    def resolve(self, spec: ModelSpec) -> ResolvedModel:
        """Construct the concrete model and wrap it in a ``ResolvedModel``."""
