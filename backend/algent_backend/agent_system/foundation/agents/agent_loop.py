"""
Base agent loop orchestrator.

This is intentionally minimal; specific strategies (ReAct, debate, trees) will
be implemented under `loops/`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .state_manager import ConversationState


LoopHook = Callable[[ConversationState], None]


@dataclass
class AgentLoop:
    """
    Skeleton for a single-agent loop.

    Subclasses or delegates can override `plan`, `act`, and `observe`.
    """

    name: str
    hooks: List[LoopHook] = field(default_factory=list)

    def run(self, state: Optional[ConversationState] = None) -> ConversationState:
        """Execute one loop iteration (placeholder)."""
        state = state or ConversationState()
        state.log(f"Loop {self.name} start")
        for hook in self.hooks:
            hook(state)
        state.log(f"Loop {self.name} end")
        return state
