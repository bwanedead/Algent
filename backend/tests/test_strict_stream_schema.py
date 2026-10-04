"""
A streamed structured request must carry the SAME strict-valid schema the non-streaming parse path does.

LangChain sends a pydantic class streamed as a bare ``model_json_schema()`` with ``strict: true``;
OpenAI rejects it ("'additionalProperties' is required to be supplied and to be false") for any model
with a nested object or a defaulted field. That 400 emptied every intel-daily section and ended the
article draft's structured step with no draft body. ``strict_stream`` repairs it; these tests prove it
for every pydantic model the codebase asks structured output for, over a mocked wire (no network).
"""

from __future__ import annotations

import importlib
import json
from typing import Any

import httpx
import pytest
from langchain_core.messages import HumanMessage

from algent_backend.agent_system.foundation.models.budget_gate import gate_chat_model

A = "algent_backend.agent_system.agents."
#: (module, class) for every with_structured_output / response_format model in the codebase.
STRUCTURED_MODELS = [
    (A + "intel.contracts", "SectionDraft"), (A + "intel.contracts", "DaySummary"),
    (A + "intel.contracts", "Brief"), (A + "intel.heat", "TheaterPlan"),
    (A + "intel.forecasts", "ResolutionPlan"),
    (A + "insight.contemplate", "Brief"), (A + "insight.contracts", "Critique"),
    (A + "insight.contracts", "InsightSpec"),
    (A + "editorial.draft", "DraftPayload"), (A + "editorial.treatment", "EditorialTreatment"),
    (A + "editorial.review_contracts", "TreatmentReview"), (A + "editorial.caveat_contracts", "CaveatCheck"),
    (A + "editorial.comprehension_contracts", "ComprehensionCheck"), (A + "editorial.compress", "Compressed"),
    (A + "editorial.headline_contracts", "Headline"), (A + "editorial.figure_images", "ImagePlan"),
    (A + "editorial.real_images", "PhotoChoice"), (A + "editorial.analytics_contracts", "AnalyticsPlan"),
    (A + "editorial.analytics_confirm_contracts", "AnalyticsConfirmReport"),
    (A + "research.profile", "SignalProfile"), (A + "research.profile", "ProfileAdditions"),
    (A + "discovery.portfolio", "ResearchPortfolio"), (A + "discovery.rake.contracts", "RakeChunkResult"),
    (A + "review.contracts", "ReviewReport"), (A + "routing.contracts", "RouteRanking"),
    (A + "radar.contracts", "RadarSweep"), (A + "radar.enrich", "EnrichedPost"),
    (A + "radar.review", "QueueReview"),
    (A + "pulse.seed", "AttachPlan"), (A + "pulse.seed", "SituationDraft"),
    (A + "pulse.update", "UpdatePlan"), (A + "pulse.registry", "Verdict"),
    (A + "pulse.registry", "Placement"), (A + "pulse.reassess", "Reading"),
    (A + "pulse.reassess", "WatchVerdict"),
]


def _strict_violations(node: Any, path: str = "") -> list[str]:
    """Provider strict rules: every object closed (additionalProperties false), all properties required."""
    bad: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            props = set(node.get("properties", {}))
            if node.get("additionalProperties") is not False:
                bad.append(f"{path or '<root>'}: additionalProperties is not false")
            if set(node.get("required", [])) != props:
                bad.append(f"{path or '<root>'}: not required {sorted(props - set(node.get('required', [])))}")
        for key, value in node.items():
            bad += _strict_violations(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            bad += _strict_violations(value, f"{path}[{i}]")
    return bad


def _streamed_request_for(schema: type) -> dict:
    pytest.importorskip("langchain_openai")
    from langchain_openai import ChatOpenAI

    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "stop here", "type": "invalid_request_error"}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = ChatOpenAI(model="m", api_key="t", base_url="http://mock/v1", http_client=http,
                        use_responses_api=True, reasoning_effort="medium", streaming=False, max_retries=0)
    twin = client.model_copy(update={"streaming": True, "stream_usage": True})
    gated = gate_chat_model(client, model_id="gpt-5.4-mini", stream_inner=twin, stream_structured=True)
    with pytest.raises(Exception):  # noqa: B017, PT011 — the mock refuses; only the request matters
        gated.with_structured_output(schema).invoke([HumanMessage(content="x")])
    assert sent and sent[0].get("stream") is True
    return sent[0]


@pytest.mark.parametrize("module,name", STRUCTURED_MODELS, ids=[n for _, n in STRUCTURED_MODELS])
def test_streamed_structured_request_carries_a_strict_valid_schema(module: str, name: str) -> None:
    schema = getattr(importlib.import_module(module), name)
    fmt = _streamed_request_for(schema)["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["name"] == name
    assert _strict_violations(fmt["schema"]) == []


def test_streamed_schema_matches_what_the_parse_path_sends() -> None:
    """The same schema (modulo the SDK's own naming) as the non-streaming ``responses.parse`` path."""
    from openai.lib._pydantic import to_strict_json_schema

    from algent_backend.agent_system.agents.intel.contracts import SectionDraft

    assert _streamed_request_for(SectionDraft)["text"]["format"]["schema"] == to_strict_json_schema(SectionDraft)


def test_the_unfixed_langchain_path_really_was_invalid() -> None:
    """Guards the guard: LangChain's own streamed schema for SectionDraft breaks the strict rules."""
    from algent_backend.agent_system.agents.intel.contracts import SectionDraft

    assert _strict_violations(SectionDraft.model_json_schema()) != []


def test_streamed_reply_is_validated_back_into_the_model_and_prose_is_rejected() -> None:
    from algent_backend.agent_system.agents.intel.contracts import SectionDraft
    from algent_backend.agent_system.foundation.models.strict_stream import _parse_reply
    from langchain_core.messages import AIMessage

    ok = _parse_reply(SectionDraft, AIMessage(content=SectionDraft(bottom_line="x").model_dump_json()))
    assert isinstance(ok["parsed"], SectionDraft)
    assert _parse_reply(SectionDraft, AIMessage(content=""))["parsed"] is None
    with pytest.raises(Exception, match="(?i)invalid json|validation error"):
        _parse_reply(SectionDraft, AIMessage(content="I compiled the section."))
