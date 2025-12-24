"""
Algo Lab algorithms package.

Keep this module thin: only re-export registry/types for convenience.
"""
from .registry import list_available, run
from .types import AlgorithmDescriptor

__all__ = ["AlgorithmDescriptor", "list_available", "run"]
