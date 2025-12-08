"""
Conversation and state helpers.

The state manager coordinates memories, scratchpads, and summaries for loops.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class ConversationState:
    """In-memory log of loop turns."""

    messages: List[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        """Append a message to the state."""
        self.messages.append(message)

