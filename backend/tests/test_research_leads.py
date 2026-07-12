"""Tests for the backfeed loop — dedup, provenance, damping (the review's three constraints)."""

from __future__ import annotations

from algent_backend.agent_system.agents.research.leads import (
    JsonLeadStore,
    backfeed_leads,
    is_covered,
    lead_id,
    open_leads_for_discovery,
)
from algent_backend.agent_system.agents.research.profile import (
    DerivedLead,
    Entity,
    SignalProfile,
)


def _lead(title, url="", entities=None, confidence="high", origin="", stage="") -> DerivedLead:
    return DerivedLead(id="local", title=title, source_url=url, entities=entities or [],
                       confidence=confidence, lead_origin=origin, created_by_stage=stage)


def test_backfeed_content_addresses_and_dedups(tmp_path) -> None:
    store = JsonLeadStore(tmp_path)
    a = _lead("Regional bank stress spreads", "https://x.com/a")
    a2 = _lead("Regional bank stress spreads", "https://x.com/a")  # same story, re-emitted
    b = _lead("A different story", "https://y.com/b")
    ids = backfeed_leads([a, a2, b], stage="signal_profile", store=store)

    assert lead_id(a) == lead_id(a2)               # content-addressed: same story -> same id
    assert len(store.list_open()) == 2             # the duplicate collapsed
    assert ids[0] == ids[1]                        # both mapped to the one id


def test_backfeed_stamps_provenance(tmp_path) -> None:
    store = JsonLeadStore(tmp_path)
    backfeed_leads([_lead("x", "u")], stage="signal_profile", store=store)
    saved = store.list_open()[0]
    assert saved.lead_origin == "research_backfeed" and saved.created_by_stage == "signal_profile"


def test_open_leads_is_damped_and_confidence_ordered(tmp_path) -> None:
    store = JsonLeadStore(tmp_path)
    backfeed_leads(
        [_lead("low one", "u1", confidence="low"), _lead("high one", "u2", confidence="high"),
         _lead("med one", "u3", confidence="medium")],
        stage="s", store=store)
    top = open_leads_for_discovery(store, limit=2)
    assert len(top) == 2 and top[0].title == "high one"   # damping + higher confidence first


def test_consumed_leads_leave_the_open_queue_and_do_not_resurrect(tmp_path) -> None:
    store = JsonLeadStore(tmp_path)
    [lid] = backfeed_leads([_lead("consume me", "u")], stage="s", store=store)
    store.mark_consumed(lid)
    assert store.list_open() == []
    backfeed_leads([_lead("consume me", "u")], stage="s", store=store)  # re-emitted
    assert store.list_open() == []                # a consumed lead is not resurrected


def test_is_covered_skips_a_lead_already_in_a_profile() -> None:
    prof = SignalProfile(id="p", title="t", entities=[
        Entity(id="e1", name="Federal Reserve"), Entity(id="e2", name="Jerome Powell")])
    covered = _lead("Fed leadership", entities=["Federal Reserve", "Jerome Powell"])
    fresh = _lead("Unrelated tech merger", entities=["Acme Corp", "Beta Inc"])
    assert is_covered(covered, [prof]) is True
    assert is_covered(fresh, [prof]) is False
    # ...and open_leads_for_discovery drops the covered one when profiles are supplied.
    store_leads = [covered, fresh]
    assert not is_covered(fresh, [prof])
    assert all(not is_covered(le, []) for le in store_leads)  # no profiles -> nothing dropped
