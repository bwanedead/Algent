"""
Prompting — system-prompt layers and task-message stitching, kept distinct.

Two separate concerns live here:

- *System prompt*: the agent's identity, composed from ordered layers broad to
  specific (a universal layer for every agent, then family/class, then per-agent
  specialization, to any depth). ``compose_system_prompt`` assembles them. Each
  layer is its own findable text module so surfaces can be edited in isolation.
- *Task message*: the per-run payload, including the optional query seed a caller
  provides, stitched from conditional segments by ``stitch_message``.

Identity is not the same as this run's task; the two never share a surface. This
package is pure text and string assembly — no LangChain/LangGraph, no agent or
runtime imports.
"""

from .base import UNIVERSAL_AGENT_BASE
from .compose import compose_system_prompt, stitch_message

__all__ = ["UNIVERSAL_AGENT_BASE", "compose_system_prompt", "stitch_message"]
