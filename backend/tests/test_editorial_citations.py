"""Tests for the deterministic citation/accuracy harness + the shared grounding floor."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial.citations import check_citations
from algent_backend.agent_system.agents.editorial.draft import ArticleDraft
from algent_backend.agent_system.agents.editorial.treatment import EditorialTreatment
from algent_backend.agent_system.agents.research.grounding import (
    cap_status_by_grounding,
    meets_grounding_floor,
)
from algent_backend.agent_system.agents.research.profile import (
    Claim,
    SignalProfile,
    Thread,
)


def _claim(cid, salience="high", grounding="snapshotted", status="confirmed") -> Claim:
    return Claim(id=cid, text=f"claim {cid}", salience=salience, grounding=grounding, status=status)


def _profile(claims, threads=None) -> SignalProfile:
    return SignalProfile(id="prof_x", title="t", claim_ledger=claims, threads=threads or [])


def _draft(cited_claims, cited_sources=None) -> ArticleDraft:
    return ArticleDraft(id="drf_x", treatment_id="trt_x", profile_id="prof_x",
                        cited_claim_ids=cited_claims, cited_source_ids=cited_sources or [])


def _treatment(must_use) -> EditorialTreatment:
    return EditorialTreatment(id="trt_x", profile_id="prof_x", must_use_items=must_use)


# -- grounding floor (shared) --------------------------------------------------

def test_grounding_floor_and_status_cap() -> None:
    weak = [_claim("c1", grounding="snippet_only")]
    strong = [_claim("c1", grounding="snapshotted")]
    assert not meets_grounding_floor(weak, [])
    assert meets_grounding_floor(strong, [])
    # A profile may not CLAIM maturity while a load-bearing claim is snippet-only.
    assert cap_status_by_grounding("complete", weak, []) == "needs_verification"
    assert cap_status_by_grounding("complete", strong, []) == "complete"
    assert cap_status_by_grounding("draft", weak, []) == "draft"  # non-mature status untouched


def test_low_salience_snippet_does_not_trip_the_floor() -> None:
    # Snippets are fine on inconsequential (low-salience) scouting residue.
    claims = [_claim("c1", salience="low", grounding="snippet_only")]
    assert meets_grounding_floor(claims, [])
    assert cap_status_by_grounding("complete", claims, []) == "complete"


def test_medium_salience_snippet_trips_the_floor() -> None:
    # "Snippets discover, reads persist": a MEDIUM (consequential) snippet claim is a violation.
    claims = [_claim("c1", salience="medium", grounding="snippet_only")]
    assert not meets_grounding_floor(claims, [])
    assert cap_status_by_grounding("complete", claims, []) == "needs_verification"


# -- citation harness ----------------------------------------------------------

def test_grounded_when_must_use_present_and_deep_read() -> None:
    prof = _profile([_claim("c1"), _claim("c2")])
    r = check_citations(_draft(["c1", "c2"]), _treatment(["c1", "c2"]), prof)
    assert r.verdict == "grounded" and r.promotable()
    assert r.must_use_missing == [] and r.weak_load_bearing == []
    assert r.grounding_tally["snapshotted"] == 2


def test_needs_deep_read_when_load_bearing_claim_is_snippet_only() -> None:
    prof = _profile([_claim("c1", grounding="snippet_only")])
    r = check_citations(_draft(["c1"]), _treatment(["c1"]), prof)
    assert r.verdict == "needs_deep_read" and not r.promotable()
    assert r.weak_load_bearing == ["c1"]


def test_drops_must_use_is_the_worst_verdict() -> None:
    prof = _profile([_claim("c1"), _claim("c2", grounding="snippet_only")])
    # cites only c1; c2 is a required must-use item that got dropped -> worst verdict wins.
    r = check_citations(_draft(["c1"]), _treatment(["c1", "c2"]), prof)
    assert r.verdict == "drops_must_use"
    assert r.must_use_missing == ["c2"] and r.must_use_present == ["c1"]


def test_must_use_thread_covered_via_its_claims() -> None:
    prof = _profile([_claim("c1")], threads=[Thread(id="t1", title="strand", claims=["c1"])])
    # must-use is the THREAD; the draft cites a claim that grounds it -> covered.
    r = check_citations(_draft(["c1"]), _treatment(["t1"]), prof)
    assert r.must_use_present == ["t1"] and r.verdict == "grounded"


def test_overstatement_flags_non_confirmed_cited_claims() -> None:
    prof = _profile([_claim("c1", status="contested"), _claim("c2", status="confirmed")])
    r = check_citations(_draft(["c1", "c2"]), _treatment([]), prof)
    assert r.overstatement_flags == ["c1"]     # contested claim flagged for hedging check
    assert r.verdict == "grounded"             # grounding is fine; hedging is the reviewer's job
