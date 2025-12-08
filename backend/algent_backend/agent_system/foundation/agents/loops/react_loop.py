"""
Prototype ReAct-style loop.

The real implementation will coordinate planning, tool usage, and reflection.
"""
from ..agent_loop import AgentLoop
from ..state_manager import ConversationState


class ReactLoop(AgentLoop):
    """Concrete loop that simply annotates its steps for now."""

    def run(self, state: ConversationState | None = None) -> ConversationState:
        state = state or ConversationState()
        state.log("ReAct loop step: observe")
        state.log("ReAct loop step: think")
        state.log("ReAct loop step: act")
        return super().run(state)
