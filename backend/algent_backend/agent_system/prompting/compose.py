"""
Prompt composition — assemble ordered layers into one system prompt.

Layers run broad to specific (universal -> family -> specialization -> ...). Any
number may be passed, so specialization can go as deep as it needs. Blank layers
are skipped so an optional layer can be passed unconditionally.
"""

from __future__ import annotations

_SEPARATOR = "\n\n"


def compose_system_prompt(*layers: str) -> str:
    """Join non-empty prompt layers, in order, into a single system prompt."""
    return _SEPARATOR.join(layer.strip() for layer in layers if layer and layer.strip())
