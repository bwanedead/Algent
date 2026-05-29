"""
Model resolution targets.

A target is one implementation path for turning a ``ModelSpec`` into a concrete
model object. ``langchain`` is the only target today; a ``native`` direct-SDK
target can be added later as a new module without touching ``ModelSpec`` or
callers.
"""

from .base import ModelTarget
from .langchain import LangChainTarget

__all__ = ["ModelTarget", "LangChainTarget"]
