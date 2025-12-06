"""
Command schema definitions.

Keep this independent of transport concerns so it can be used by both HTTP and
in-process agents.
"""
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Command:
    """Structured action request."""

    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str | None = None  # e.g., "ui", "agent", "script"

