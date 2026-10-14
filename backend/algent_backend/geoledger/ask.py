"""
The structured model call the extractor is given (``ask(schema, role, task) -> instance``), for the entry points that
have no daily context to borrow one from (the ``newsroom geo`` commands). The daily passes its own ``_ask`` instead.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def extraction_spec() -> Any:
    """The house model at low effort: extraction is reading, not reasoning, so it is the cheap setting."""
    from algent_backend.agent_system.foundation.models import house_spec

    return house_spec(reasoning_effort="low", temperature=0.1, max_tokens=8192)


def house_ask() -> Callable[[Any, str, str], Any]:
    """An ``ask`` over the house model (see ``extraction_spec``)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.foundation.models import ModelResolver
    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    resolver = ModelResolver()
    spec = extraction_spec()

    def ask(schema: Any, role: str, task: str) -> Any:
        model = resolver.resolve(spec).client.with_structured_output(schema)
        return model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, role)), HumanMessage(content=task)])

    return ask
