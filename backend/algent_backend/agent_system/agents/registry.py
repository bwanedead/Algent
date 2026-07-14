"""
AgentRegistry — the known agent catalog.

A small, explicit in-memory map of ``agent_id`` to ``AgentSpec``. No dynamic
discovery, plugin system, or filesystem scanning — agents are registered in code.

``get`` raises ``ValueError`` for an unknown agent, mirroring
``RuntimeRegistry.get``. The orchestration layer (``RunService``) catches that
and returns a failed ``RunResult`` rather than letting the exception escape.
"""

from __future__ import annotations

from .agent_spec import AgentSpec


class AgentRegistry:
    """Selects an ``AgentSpec`` by id."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}

    def register(self, spec: AgentSpec) -> None:
        self._agents[spec.agent_id] = spec

    def get(self, agent_id: str) -> AgentSpec:
        spec = self._agents.get(agent_id)
        if spec is None:
            known = ", ".join(sorted(self._agents)) or "(none)"
            raise ValueError(f"Unknown agent '{agent_id}'. Known agents: {known}.")
        return spec

    def list(self) -> list[AgentSpec]:
        return list(self._agents.values())


def default_agent_registry() -> AgentRegistry:
    """Build the registry with the agents Algent ships by default."""
    # Imported lazily so merely importing the registry class does not pull an
    # agent's graph module (and its LangGraph imports) into memory.
    from .discovery.general.spec import SPEC as general_discovery_spec
    from .discovery.synthesis.spec import SPEC as discovery_synthesis_spec
    from .editorial.analytics_spec import SPEC as analytics_router_spec
    from .editorial.caveat_spec import SPEC as caveat_reviewer_spec
    from .editorial.draft_gauntlet_spec import SPEC as drafting_gauntlet_spec
    from .editorial.draft_spec import SPEC as article_drafter_spec
    from .editorial.gauntlet_spec import SPEC as planning_gauntlet_spec
    from .editorial.headline_spec import SPEC as headline_writer_spec
    from .editorial.pipeline_spec import SPEC as editorial_pipeline_spec
    from .editorial.review_spec import SPEC as treatment_reviewer_spec
    from .editorial.spec import SPEC as editorial_planner_spec
    from .enrich.counter_perspective import SPEC as enrich_counter_perspective_spec
    from .enrich.primary_source import SPEC as enrich_primary_source_spec
    from .gauntlet.spec import SPEC as profile_gauntlet_spec
    from .hello_workflow.spec import SPEC as hello_workflow_spec
    from .news_brief.spec import SPEC as news_brief_spec
    from .newsroom.rail_spec import SPEC as newsroom_rail_spec
    from .research.spec import SPEC as signal_profile_spec
    from .review.spec import SPEC as profile_reviewer_spec
    from .routing.spec import SPEC as signal_router_spec

    registry = AgentRegistry()
    registry.register(hello_workflow_spec)
    registry.register(news_brief_spec)
    registry.register(general_discovery_spec)
    registry.register(discovery_synthesis_spec)
    registry.register(signal_router_spec)
    registry.register(signal_profile_spec)
    registry.register(profile_reviewer_spec)
    registry.register(editorial_planner_spec)
    registry.register(treatment_reviewer_spec)
    registry.register(planning_gauntlet_spec)
    registry.register(article_drafter_spec)
    registry.register(caveat_reviewer_spec)
    registry.register(analytics_router_spec)
    registry.register(headline_writer_spec)
    registry.register(drafting_gauntlet_spec)
    registry.register(editorial_pipeline_spec)
    registry.register(enrich_primary_source_spec)
    registry.register(enrich_counter_perspective_spec)
    registry.register(profile_gauntlet_spec)
    registry.register(newsroom_rail_spec)
    return registry
