"""
Algent backend package.

Houses the core agent ecosystem (`agent_system`), pluggable labs (`labs`), API
surface, commands, and config machinery.
"""

from . import agent_system, labs  # noqa: F401
