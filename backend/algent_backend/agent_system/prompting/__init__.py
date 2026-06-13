"""
Prompting — shared, layered system-prompt surfaces.

Prompts are composed from ordered layers, broad to specific: a universal layer
that applies to every agent, then family/class layers, then per-agent
specialization, to as many layers as a specialization needs. Each layer is its
own findable text module so prompt surfaces can be edited in isolation; the
``compose_system_prompt`` helper assembles them.

This package is pure text and string assembly — no LangChain/LangGraph, no agent
or runtime imports.
"""

from .base import UNIVERSAL_AGENT_BASE
from .compose import compose_system_prompt

__all__ = ["UNIVERSAL_AGENT_BASE", "compose_system_prompt"]
