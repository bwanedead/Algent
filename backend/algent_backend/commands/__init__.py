"""
Command models and dispatch.

Commands are the shared contract between the UI, automation/agents, and the
backend. They should remain small, explicit, and versionable.
"""
from .models import Command  # noqa: F401
from .dispatcher import CommandDispatcher  # noqa: F401

