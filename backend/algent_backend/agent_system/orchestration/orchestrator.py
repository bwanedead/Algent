"""
Multi-agent orchestration placeholder.
"""
from dataclasses import dataclass, field
from typing import List

from ..foundation.agents.agent_loop import AgentLoop


@dataclass
class Orchestrator:
    """Runs multiple loops (possibly in parallel later)."""

    loops: List[AgentLoop] = field(default_factory=list)

    def run_all(self) -> None:
        """Run each registered loop sequentially."""
        for loop in self.loops:
            loop.run()
