"""
Route handlers (placeholder).

This module mirrors the `/health` endpoint exposed by the temporary stdlib
server. When moving to a real framework, adapt these functions to framework
handlers instead of re-writing logic.
"""
from typing import Dict


def health() -> Dict[str, str]:
    """Return a simple health payload."""
    return {"status": "ok", "service": "algent-backend"}

