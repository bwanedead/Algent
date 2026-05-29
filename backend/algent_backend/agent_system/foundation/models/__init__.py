"""
Model resolution layer.

A neutral ``ModelSpec`` (what model an agent wants) is routed by
``ModelResolver`` to a target resolver, which constructs a concrete model object
and returns it wrapped in a ``ResolvedModel`` (the object plus metadata about
what was built).

LangChain is the first and only target today; it is confined to
``targets/langchain.py``. Nothing else in the codebase should import LangChain
model wrappers.
"""

from .handles import ResolvedModel
from .resolver import ModelResolver
from .specs import ModelSpec

__all__ = ["ModelResolver", "ModelSpec", "ResolvedModel"]
