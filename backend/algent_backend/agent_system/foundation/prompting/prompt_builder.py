"""
Composable prompt builder.
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PromptComponent:
    """Small chunk of prompt text."""

    key: str
    text: str


@dataclass
class PromptBuilder:
    """Assemble prompts dynamically from registered components."""

    components: List[PromptComponent] = field(default_factory=list)

    def add(self, key: str, text: str) -> None:
        self.components.append(PromptComponent(key, text))

    def render(self, context: Dict[str, str] | None = None) -> str:
        context = context or {}
        rendered = []
        for component in self.components:
            rendered.append(component.text.format(**context))
        return "\n".join(rendered)
