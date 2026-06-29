"""Tests for the profile assembly harness (local-id rewrite, dedup, snapshots) + briefing."""

from __future__ import annotations

from algent_backend.agent_system.agents.research.assembly import finalize_profile
from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    Entity,
    SignalProfile,
    SourceArtifact,
    Thread,
)


def _authored() -> SignalProfile:
    """A profile as a model would author it: simple local ids, some duplicates + a dangling ref."""
    return SignalProfile(
        id="", title="Fed path", summary="markets see a hold",
        source_ledger=[
            SourceArtifact(id="s1", url="https://www.Reuters.com/Fed/", title="Reuters", source_type="secondary"),
            SourceArtifact(id="s2", url="http://reuters.com/fed", title="Reuters dup"),  # same source, diff url form
        ],
        claim_ledger=[
            Claim(id="c1", text="The Fed held rates", status="confirmed", salience="high",
                  supported_by=["s1", "s2", "s9"]),  # s9 is dangling
        ],
        entities=[
            Entity(id="e1", name="Federal Reserve", type="org", role="central bank"),
            Entity(id="e2", name="federal reserve", type="org"),  # same entity, different case
        ],
        threads=[
            Thread(id="t1", title="rate path", kind="force", salience="high",
                   body="...", entities=["e1", "e2"], claims=["c1"], sources=["s1"]),
        ],
    )


def test_assembly_rewrites_refs_dedupes_and_stamps() -> None:
    captured = {"reuters.com/fed": {"content_hash": "sha256:real", "excerpt": "fed held", "captured_at": "t"}}
    out = finalize_profile(
        _authored(), {"id": "vec_abc123"}, captured,
        model="gpt-5.4-mini", generator="signal_profile@v2", stage="signal_profile",
    )

    # content-addressed source dedup: s1 and s2 collapse to one
    assert len(out.source_ledger) == 1
    sid = out.source_ledger[0].id
    assert sid.startswith("src_")
    # claim refs rewritten to the stable id; the dangling s9 dropped; dedup'd
    assert out.claim_ledger[0].supported_by == [sid]
    # entity dedup (same canonical name+type) -> one
    assert len(out.entities) == 1
    eid = out.entities[0].id
    assert out.entities[0].canonical_name == "Federal Reserve"
    # thread refs rewritten to stable ids (entities deduped to one)
    assert out.threads[0].entities == [eid]
    assert out.threads[0].claims == [out.claim_ledger[0].id]
    # harness snapshot attached by NORMALIZED url (matched despite www/case/scheme)
    assert out.source_ledger[0].snapshot is not None
    assert out.source_ledger[0].snapshot.content_hash == "sha256:real"
    # provenance stamped on items + profile id/parent from the vector
    assert out.claim_ledger[0].provenance.added_by_stage == "signal_profile"
    assert out.id == "prof_abc123" and out.parent_vector_id == "vec_abc123"


def test_assembly_discards_model_fabricated_snapshots() -> None:
    from algent_backend.agent_system.agents.research.profile import SourceSnapshot

    p = SignalProfile(id="", title="t", source_ledger=[
        SourceArtifact(id="s1", url="https://ex.com/a",
                       snapshot=SourceSnapshot(content_hash="sha256:FAKE")),  # model fabricated
    ])
    out = finalize_profile(p, {"id": "vec_x"}, {}, model="m", generator="g", stage="signal_profile")
    assert out.source_ledger[0].snapshot is None  # no real capture -> discarded


def test_briefing_renders_salience_first_and_drills() -> None:
    captured = {"reuters.com/fed": {"content_hash": "sha256:real", "excerpt": "e", "captured_at": "t"}}
    out = finalize_profile(_authored(), {"id": "vec_abc"}, captured, model="m", generator="g", stage="s")
    md = render_briefing(out)
    assert md.startswith("# Fed path")
    assert "## What's going on (the field)" in md and "rate path" in md
    assert "## Evidence (claims)" in md and "[confirmed] The Fed held rates" in md
    assert "[snapshot]" in md  # the snapshotted source is marked
