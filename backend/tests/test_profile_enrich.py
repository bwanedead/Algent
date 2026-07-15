"""Tests for the merge harness + the primary_source enricher (the gauntlet's enrich step)."""

from __future__ import annotations

from algent_backend.agent_system.agents.enrich import base as enrich_base
from algent_backend.agent_system.agents.research.assembly import finalize_profile, merge_additions
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    Entity,
    ProfileAdditions,
    SignalProfile,
    SourceArtifact,
    Thread,
)
from algent_backend.agent_system.agents.review.contracts import ReviewFinding, ReviewReport
from algent_backend.agent_system.foundation.models import ModelSpec
from algent_backend.agent_system.runs.context import AgentRunContext


def _existing() -> SignalProfile:
    return finalize_profile(
        SignalProfile(
            id="", title="Fed path",
            source_ledger=[SourceArtifact(id="s1", url="https://poly.com/x", publisher="Polymarket")],
            claim_ledger=[Claim(id="c1", text="markets expect a hold", salience="high", supported_by=["s1"])],
        ),
        {"id": "vec_z"}, {"poly.com/x": {"content_hash": "sha256:old", "excerpt": "e", "captured_at": "t"}},
        model="m", generator="signal_profile@v2", stage="signal_profile",
    )


def test_merge_is_additive_dedups_and_preserves_verified_snapshots() -> None:
    existing = _existing()
    existing_claim_id = existing.claim_ledger[0].id
    assert existing.source_ledger[0].snapshot.content_hash == "sha256:old"  # verified upstream

    additions = ProfileAdditions(
        sources=[
            SourceArtifact(id="ns1", url="https://fed.gov/data", publisher="Federal Reserve", source_type="primary"),
            SourceArtifact(id="ns2", url="http://poly.com/x"),  # dup of existing -> dedup
        ],
        claims=[Claim(id="nc1", text="primary data confirms a hold", salience="high", supported_by=["ns1"])],
        threads=[Thread(id="nt1", title="primary grounding", body="b", claims=[existing_claim_id, "nc1"])],
        entities=[Entity(id="ne1", name="Federal Reserve", type="org", role="central bank")],  # entities have no provenance
        addressed_findings=["find_01"],
    )
    merged = merge_additions(
        existing, additions, {"fed.gov/data": {"content_hash": "sha256:new", "excerpt": "e2", "captured_at": "t2"}},
        generator="enrich_primary_source@v1", stage="primary_source_enricher",
    )

    assert merged.id == existing.id and merged.revision == 2 and merged.profile_status == "enriching"
    urls = {s.url for s in merged.source_ledger}
    assert "https://fed.gov/data" in urls and len(merged.source_ledger) == 2  # added + dup collapsed
    poly = next(s for s in merged.source_ledger if "poly" in s.url)
    assert poly.snapshot.content_hash == "sha256:old"   # existing verified snapshot PRESERVED
    fed = next(s for s in merged.source_ledger if "fed" in s.url)
    assert fed.snapshot.content_hash == "sha256:new" and fed.source_type == "primary"  # new capture
    nc = next(c for c in merged.claim_ledger if "primary data confirms" in c.text)
    assert nc.grounding == "snapshotted"  # grounded by the deep-read primary source
    assert nc.provenance.added_by_stage == "primary_source_enricher" and nc.provenance.revision == 2
    ec = next(c for c in merged.claim_ledger if c.id == existing_claim_id)
    assert ec.provenance.added_by_stage == "signal_profile"  # existing item keeps its provenance
    assert existing_claim_id in merged.threads[0].claims and nc.id in merged.threads[0].claims  # links resolve
    assert any(e.name == "Federal Reserve" for e in merged.entities)  # entity merged (no provenance field)


# -- the enricher graph --------------------------------------------------------

class _Resolver:
    def resolve(self, _spec):
        return type("R", (), {"client": object()})()


def _ctx(events):
    return AgentRunContext(
        run_id="t", model_resolver=_Resolver(),  # type: ignore[arg-type]
        tools={"web_search": object()}, emit=lambda et, p=None: events.append((et, p or {})),
    )


def _graph(context, monkeypatch, produced):
    monkeypatch.setattr(enrich_base, "build_react_loop", lambda *a, **k: object())
    monkeypatch.setattr(enrich_base, "stream_react_loop", lambda *a, **k: produced)
    return enrich_base.build_enrich_graph(
        context, lane="primary_source", model_spec=ModelSpec(provider="openai", model="gpt-5.4-mini"),
        tool_ids=("web_search",), system_prompt="sys", search_channels=("keyword", "read"),
        paid_budget=2, cost_cap_usd=1.0,
    )


def _review() -> dict:
    return ReviewReport(id="r", profile_id="prof_z", findings=[
        ReviewFinding(id="find_01", type="missing_primary_source", severity="high",
                      target="profile", lane="primary_source", maturity_blocker=True),
    ]).model_dump()


def test_enrich_graph_merges_bumps_revision_and_persists(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ALGENT_PROFILE_STORE", str(tmp_path))
    additions = ProfileAdditions(
        sources=[SourceArtifact(id="ns1", url="https://fed.gov/d", source_type="primary")],
        claims=[Claim(id="nc1", text="primary confirms", supported_by=["ns1"])],
        addressed_findings=["find_01"],
    )
    events: list = []
    graph = _graph(_ctx(events), monkeypatch, additions)

    out = graph.invoke({"profile": _existing().model_dump(), "review": _review()})

    assert out["profile"]["revision"] == 2  # merged + bumped
    assert any(s["url"] == "https://fed.gov/d" for s in out["profile"]["source_ledger"])
    done = next(p for et, p in events if et == "enrich.completed")
    assert done["added_sources"] == 1 and done["addressed"] == ["find_01"]
    assert "estimated_usd" in done   # enrichment surfaces its spend (the rail sums it)


def test_counter_perspective_lane_registered_and_distinct() -> None:
    from algent_backend.agent_system.agents.enrich.prompts import (
        COUNTER_PERSPECTIVE_PROMPT,
        PRIMARY_SOURCE_PROMPT,
    )
    from algent_backend.agent_system.agents.registry import default_agent_registry

    spec = default_agent_registry().get("enrich_counter_perspective")
    assert spec.tool_ids == ("web_search",)
    assert spec.test_fixture.input_file.endswith("enrich_input_sample.json")
    # the lanes share the engine but carry distinct doctrine
    assert "COUNTER-PERSPECTIVE" in COUNTER_PERSPECTIVE_PROMPT and "steelman" in COUNTER_PERSPECTIVE_PROMPT
    assert COUNTER_PERSPECTIVE_PROMPT != PRIMARY_SOURCE_PROMPT


def test_enrich_graph_no_findings_for_lane_is_a_noop(monkeypatch) -> None:
    events: list = []
    graph = _graph(_ctx(events), monkeypatch, ProfileAdditions())
    review = ReviewReport(id="r", findings=[
        ReviewFinding(id="f1", type="needs_data", lane="analytics"),  # different lane
    ]).model_dump()
    out = graph.invoke({"profile": _existing().model_dump(), "review": review})
    assert out["profile"]["revision"] == 1  # unchanged
    assert any(et == "enrich.no_work" for et, _ in events)
