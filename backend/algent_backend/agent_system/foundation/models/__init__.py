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
from .openai_defaults import DEFAULT_OPENAI_MODEL, openai_model_id, openai_spec
from .resolver import ModelResolver
from .specs import ModelSpec, ReasoningEffort

__all__ = [
    "DEFAULT_OPENAI_MODEL",
    "ModelResolver",
    "ModelSpec",
    "ReasoningEffort",
    "ResolvedModel",
    "openai_model_id",
    "openai_spec",
]
