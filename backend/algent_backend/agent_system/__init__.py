"""
Agent system package.

This umbrella houses the core infrastructure that powers every lab or work
vector: agent loops, model providers, tool bridges, and orchestration helpers.
"""

from .foundation import agents, models, prompting  # noqa: F401
from .integration import tool_registry  # noqa: F401
from .orchestration import orchestrator  # noqa: F401
