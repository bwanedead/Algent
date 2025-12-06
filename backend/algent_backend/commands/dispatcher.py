"""
Minimal command dispatcher.

This is intentionally simple; replace with a more robust bus/queue when needed.
"""
from typing import Callable, Dict

from .models import Command

CommandHandler = Callable[[Command], dict]


class CommandDispatcher:
    """Routes commands to handlers."""

    def __init__(self) -> None:
        self._handlers: Dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        """Register a handler for a command name."""
        # TODO: add validation/versioning.
        self._handlers[name] = handler

    def dispatch(self, command: Command) -> dict:
        """Dispatch a command to its handler or return a not-implemented payload."""
        handler = self._handlers.get(command.name)
        if not handler:
            return {
                "status": "unhandled",
                "message": f"No handler registered for '{command.name}'",
            }
        return handler(command)

