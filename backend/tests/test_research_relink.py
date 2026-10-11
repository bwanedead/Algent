"""Dangling-ref signal, the one relink pass, and harness-owned provenance."""

from __future__ import annotations

import pytest

from algent_backend.agent_system.agents.intel import brief as br
from algent_backend.agent_system.agents.research.assembly import finalize_profile
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    DanglingRefs,
    ItemProvenance,
    SignalProfile,
    SourceArtifact,
)
from algent_backend.agent_system.agents.research.relink import ClaimLinks, Relink, claims_lost_their_links, relink


def _built(claim_refs: list[str]) -> SignalProfile:
    p = SignalProfile(
        id="", title="t",
        source_ledger=[SourceArtifact(id="s1", url="https://a.com", title="A"),
                       SourceArtifact(id="s2", url="https://b.com", title="B")],
        claim_ledger=[Claim(id="c1", text="one", supported_by=claim_refs)],
    )
    return finalize_profile(p, {"id": "v"}, {}, model="m", generator="g", stage="signal_profile")


class _Model:
    def __init__(self, answer=None, boom=False):
        self.answer, self.boom = answer, boom

    def with_structured_output(self, _schema):
        return self

    def invoke(self, *_a, **_k):
        if self.boom:
            raise RuntimeError("down")
        return self.answer


def test_dangling_refs_are_counted() -> None:
    assert _built(["s1", "s9", "s8"]).link_audit.dangling == [DanglingRefs(kind="claim.supported_by", count=2)]
    assert _built(["s1"]).link_audit.dangling == []


def test_complete_profile_needs_no_relink() -> None:
    assert not claims_lost_their_links(_built(["s1"]))
    assert claims_lost_their_links(_built([]))


def test_relink_attaches_valid_ids_and_ignores_invented() -> None:
    p = _built([])
    cid, sid = p.claim_ledger[0].id, p.source_ledger[0].id
    out = relink(p, _Model(Relink(links=[ClaimLinks(claim_id=cid, source_ids=[sid, "src_invented"])])))
    assert out.claim_ledger[0].supported_by == [sid]
    assert out.is_complete and out.link_audit.relink_attempted and out.link_audit.claims_relinked == 1


def test_relink_with_nothing_valid_leaves_profile_incomplete() -> None:
    p = _built([])
    out = relink(p, _Model(Relink(links=[ClaimLinks(claim_id=p.claim_ledger[0].id, source_ids=["nope"])])))
    assert not out.is_complete and out.link_audit.relink_attempted and out.link_audit.claims_relinked == 0
    assert not relink(p, _Model(boom=True)).is_complete


def test_empty_research_message_names_the_relink_attempt(monkeypatch) -> None:
    p = relink(_built([]), _Model(Relink()))

    class _G:
        def invoke(self, *_a, **_k):
            return {"profile": p.model_dump()}

    import algent_backend.agent_system.agents.research.spec as spec
    monkeypatch.setattr(spec, "build_graph", lambda _c: _G())
    theater = type("T", (), {"id": "thr_x", "name": "X", "members": [], "domain": "d", "why": "",
                             "description": ""})()
    with pytest.raises(br.EmptyResearch, match="relink pass was attempted"):
        br.commission_research(None, None, theater)


def test_model_cannot_forge_provenance() -> None:
    forged = ItemProvenance(added_by_stage="forged", revision=9, created_at="1999-01-01")
    p = SignalProfile(
        id="", title="t",
        source_ledger=[SourceArtifact(id="s1", url="https://a.com", provenance=forged)],
        claim_ledger=[Claim(id="c1", text="x", supported_by=["s1"], provenance=forged)],
    )
    out = finalize_profile(p, {"id": "v"}, {}, model="m", generator="g", stage="signal_profile")
    for item in (out.source_ledger[0], out.claim_ledger[0]):
        assert item.provenance.added_by_stage == "signal_profile" and item.provenance.created_at != "1999-01-01"
