"""Tests for the t2 signal-profile contracts and the ProfileStore boundary."""

from __future__ import annotations

from algent_backend.agent_system.agents.research import (
    Claim,
    DerivedLead,
    Entity,
    JsonProfileStore,
    SignalProfile,
    SourceArtifact,
    SourceSnapshot,
    Thread,
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
        status="confirmed", salience="high", supported_by=["src:ferc-order"],
    )
    thread = Thread(
        id="t1", title="data-center grid strain", kind="force", salience="high",
        body="AI data centers are straining grid interconnection.", entities=["e1"], claims=["c1"],
    )
    lead = DerivedLead(id="dl1", title="PJM data-center queue", why_noticed="adjacent", suggested_use="profile")
    return SignalProfile(
        id="profile:ferc-pjm", parent_vector_id="vec:1",
        title="FERC orders PJM tariff revision", profile_status="researching", as_of="2026-06-26",
        claim_ledger=[claim], source_ledger=[src],
        entities=[Entity(id="e1", name="FERC", type="org", role="regulator")],
        threads=[thread], output_recommendations=["article", "radar"], derived_leads=[lead],
        generator="signal_profile@v2", model="gpt-5.4-mini",
    )


def test_profile_roundtrips_through_json_store(tmp_path) -> None:
    store = JsonProfileStore(tmp_path)
    store.save(_profile())

    got = store.get("profile:ferc-pjm")
    assert got is not None
    assert got.id == "profile:ferc-pjm" and got.parent_vector_id == "vec:1" and got.as_of == "2026-06-26"
    assert got.schema_version == SCHEMA_VERSION == 2 and got.revision == 1
    assert got.claim_ledger[0].status == "confirmed" and got.claim_ledger[0].salience == "high"
    assert got.claim_ledger[0].supported_by == ["src:ferc-order"]
    # the knowledge field round-trips
    assert got.entities[0].name == "FERC" and got.entities[0].role == "regulator"
    assert got.threads[0].kind == "force" and got.threads[0].claims == ["c1"]
    snap = got.source_ledger[0].snapshot
    assert snap is not None and snap.content_hash == "abc123" and snap.full_text_path == "snapshots/ferc.txt"
    assert got.output_recommendations == ["article", "radar"]

    assert store.list_ids() == ["profile:ferc-pjm"]
    assert store.get("missing") is None


def test_profile_graph_slots_default_empty() -> None:
    p = SignalProfile(id="p", title="t")
    assert p.derived_leads == [] and p.corpus_context == [] and p.threads == []  # empty slots
    assert p.timeline == [] and p.watch_triggers == []  # flat fields (modules flattened in v2)
    assert p.profile_status == "draft" and p.schema_version == 2
