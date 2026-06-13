"""
Artifacts — durable outputs produced by agent runs.

An artifact is a file an agent produced on purpose (a brief, a source pool, a
topic list), not a log or a trace. ``ArtifactRef`` is the serializable pointer;
``ArtifactWriter`` puts bytes on disk inside the run's own artifacts directory.

This package is harness-owned and rail-free: it must not import LangChain,
LangGraph, or anything agent-specific.
"""

from .refs import ArtifactRef
from .writer import ArtifactWriter

__all__ = ["ArtifactRef", "ArtifactWriter"]
