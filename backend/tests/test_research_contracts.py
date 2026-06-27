"""Tests for the t2 signal-profile contracts and the ProfileStore boundary."""

from __future__ import annotations

from algent_backend.agent_system.agents.research import (
    Claim,
    DerivedLead,
    JsonProfileStore,
    SignalProfile,
    SourceArtifact,
    SourceSnapshot,
)
from algent_backend.agent_system.agents.research.profile import SCHEMA_VERSION


def _profile() -> SignalProfile:
    src = SourceArtifact(
        id="src:ferc-order", url="https://ferc.gov/order", title="FERC Order",
        publisher="FERC", source_type="primary",
        snapshot=SourceSnapshot(
            content_hash="abc123", captured_at="t", excerpt="…",
            full_text_path="snapshots/ferc.txt",  # full text by reference, not inline
        ),
    )
    claim = Claim(
        id="c1", text="FERC ordered PJM to revise its tariff",
        status="confirmed", supported_by=["src:ferc-order"],
    )
    lead = DerivedLead(id="dl1", title="PJM data-center queue", why_noticed="adjacent", suggested_use="profile")
    return SignalProfile(
        id="profile:ferc-pjm", parent_vector_id="vec:1",
        title="FERC orders PJM tariff revision", profile_status="researching",
        claim_ledger=[claim], source_ledger=[src], entities=["FERC", "PJM"],
        output_recommendations=["article", "radar"], derived_leads=[lead],
        generator="signal_profile@v0", model="gpt-5.4-mini",
    )


def test_profile_roundtrips_through_json_store(tmp_path) -> None:
    store = JsonProfileStore(tmp_path)
    store.save(_profile())

    got = store.get("profile:ferc-pjm")
    assert got is not None
    assert got.id == "profile:ferc-pjm" and got.parent_vector_id == "vec:1"
    assert got.schema_version == SCHEMA_VERSION and got.revision == 1
    assert got.claim_ledger[0].status == "confirmed"
    assert got.claim_ledger[0].supported_by == ["src:ferc-order"]
    # snapshot keeps the full text by reference, not inline
    snap = got.source_ledger[0].snapshot
    assert snap is not None and snap.content_hash == "abc123" and snap.full_text_path == "snapshots/ferc.txt"
    assert got.source_ledger[0].publisher_id is None  # reserved future hook
    assert got.output_recommendations == ["article", "radar"]
    assert got.derived_leads[0].lead_origin == "research_backfeed"

    assert store.list_ids() == ["profile:ferc-pjm"]  # authoritative id, not the safe filename
    assert store.get("missing") is None


def test_profile_graph_slots_default_empty() -> None:
    p = SignalProfile(id="p", title="t")
    assert p.derived_leads == [] and p.corpus_context == []  # graph-loop slots, empty for now
    assert p.modules.timeline == [] and p.modules.watch_triggers == []
    assert p.profile_status == "draft" and p.schema_version == SCHEMA_VERSION
