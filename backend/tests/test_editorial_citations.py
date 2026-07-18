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


def _claim(cid, salience="high", grounding="snapshotted", status="confirmed", supported_by=None) -> Claim:
    return Claim(id=cid, text=f"claim {cid}", salience=salience, grounding=grounding, status=status,
                 supported_by=supported_by or [])


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
    # A thread's grounding is harness-computed as the weakest of its claims — c1 is snapshotted, so
    # the thread is too (spelled out here because the model default is "unsourced").
    prof = _profile([_claim("c1")],
                    threads=[Thread(id="t1", title="strand", claims=["c1"], grounding="snapshotted")])
    # must-use is the THREAD; the draft cites a claim that grounds it -> covered.
    r = check_citations(_draft(["c1"]), _treatment(["t1"]), prof)
    assert r.must_use_present == ["t1"] and r.verdict == "grounded"


def test_unsourced_thread_cannot_be_must_use_either() -> None:
    # The floor is about the item, not its type: a thread grounded in nothing is equally incoherent
    # as undroppable evidence.
    prof = _profile([_claim("c1")], threads=[Thread(id="t1", title="strand", claims=[])])
    r = check_citations(_draft(["c1"]), _treatment(["t1"]), prof)
    assert r.must_use_stripped == ["t1 (unsourced)"] and r.verdict == "grounded"


def test_treatment_consequential_overrides_sandbagged_salience() -> None:
    # A claim graded "low" in the profile but declared load-bearing by the treatment (must_use)
    # is treated as consequential — the model can't sandbag salience to slip under the floor.
    prof = _profile([_claim("c1", salience="low", grounding="snippet_only", supported_by=["s1"])])
    r = check_citations(_draft(["c1"]), _treatment(["c1"]), prof)
    assert r.verdict == "needs_deep_read" and r.weak_load_bearing == ["c1"]
    assert r.deep_read_worklist == ["s1"]   # the worklist is the SOURCE to read, not the claim


def test_low_salience_snippet_not_in_treatment_is_tolerated_in_prose() -> None:
    # Same low snippet claim, but NOT declared load-bearing by the treatment -> tolerated.
    prof = _profile([_claim("c1", salience="low", grounding="snippet_only", supported_by=["s1"])])
    r = check_citations(_draft(["c1"]), _treatment([]), prof)
    assert r.verdict == "grounded" and r.weak_load_bearing == []


# -- the must-use floor: a thin item may not be made UNDROPPABLE ---------------

def test_unsourced_claim_cannot_be_must_use() -> None:
    # An unsourced claim can't be load-bearing (the grounding floor) AND simultaneously be evidence
    # the draft is forbidden to drop. The harness refuses it rather than force padding into prose.
    prof = _profile([_claim("c1"), _claim("c2", grounding="unsourced", status="unconfirmed")])
    r = check_citations(_draft(["c1"]), _treatment(["c1", "c2"]), prof)   # draft drops c2
    assert r.verdict == "grounded"                    # NOT drops_must_use — the cut is allowed
    assert r.must_use_missing == [] and r.must_use_present == ["c1"]
    assert r.must_use_stripped == ["c2 (unsourced)"]


def test_low_salience_claim_cannot_be_must_use() -> None:
    prof = _profile([_claim("c1"), _claim("c2", salience="low")])
    r = check_citations(_draft(["c1"]), _treatment(["c1", "c2"]), prof)
    assert r.verdict == "grounded" and r.must_use_stripped == ["c2 (low salience)"]


def test_must_use_is_hard_capped_at_three() -> None:
    # must_use is omission-risk insurance, not an inventory. A planner marking many claims
    # undroppable (the padding cause) is capped: the most-salient survive, the rest are the
    # drafter's judgment. Highest-salience-first so the most defensible stay enforced.
    prof = _profile([
        _claim("hi1", salience="high"), _claim("hi2", salience="high"),
        _claim("md1", salience="medium"), _claim("md2", salience="medium"),
        _claim("hi3", salience="high"),
    ])
    r = check_citations(_draft([]), _treatment(["hi1", "md1", "hi2", "md2", "hi3"]), prof)
    assert set(r.must_use_present) | set(r.must_use_missing) == {"hi1", "hi2", "hi3"}  # the 3 high ones
    assert set(m.split()[0] for m in r.must_use_stripped) == {"md1", "md2"}            # mediums over cap
    assert all("over cap" in m for m in r.must_use_stripped)


def test_the_bitcoin_case_the_drafter_may_now_cut_it() -> None:
    """Replay of the real Fed piece: the planner made a low-salience BTC claim and an UNSOURCED
    'not well established' claim must-use, so the harness forced the drafter to carry a paragraph
    that resolved to nothing. Cutting both must now be legal."""
    prof = _profile([
        _claim("clm_pce"),                                                        # the real story
        _claim("clm_btc_price", salience="low", supported_by=["s1"]),             # peripheral
        _claim("clm_btc_link", salience="medium", grounding="unsourced", status="unconfirmed"),
    ])
    treatment = _treatment(["clm_pce", "clm_btc_price", "clm_btc_link"])
    r = check_citations(_draft(["clm_pce"]), treatment, prof)                     # BTC cut entirely
    assert r.verdict == "grounded"                    # the correct editorial call is no longer punished
    assert set(r.must_use_stripped) == {"clm_btc_price (low salience)", "clm_btc_link (unsourced)"}


def test_stripped_from_must_use_is_still_held_to_the_deep_read_floor_if_cited() -> None:
    # Droppability and grounding-strength are different axes: "you need not carry this" and "if you
    # DO carry it, it must be deep-read" are both true — so sandbagging still can't slip the floor.
    prof = _profile([_claim("c1", salience="low", grounding="snippet_only", supported_by=["s1"])])
    r = check_citations(_draft(["c1"]), _treatment(["c1"]), prof)   # stripped from must_use, but cited
    assert r.must_use_stripped == ["c1 (low salience)"]
    assert r.verdict == "needs_deep_read" and r.weak_load_bearing == ["c1"]


def test_overstatement_flags_non_confirmed_cited_claims() -> None:
    prof = _profile([_claim("c1", status="contested"), _claim("c2", status="confirmed")])
    r = check_citations(_draft(["c1", "c2"]), _treatment([]), prof)
    assert r.overstatement_flags == ["c1"]     # contested claim flagged for hedging check
    assert r.verdict == "grounded"             # grounding is fine; hedging is the reviewer's job


def test_unverified_figures_catches_prose_drifting_off_its_evidence() -> None:
    # A cited claim says 81%; the prose says 83% — a live-source drift caught for free.
    prof = _profile([_claim("c1", grounding="snapshotted"), _claim("c2", grounding="snapshotted")])
    prof.claim_ledger[0].text = "Polymarket shows no change at 81%"
    prof.claim_ledger[1].text = "core PCE rose 3.4%"
    d = _draft(["c1", "c2"])
    d.body = "The hold is priced at 83%, and core PCE is 3.4%."
    r = check_citations(d, _treatment([]), prof)
    assert "83%" in r.unverified_figures        # drifted off the evidence -> flagged
    assert "3.4%" not in r.unverified_figures    # legitimately restated -> not flagged
    assert "81%" not in r.unverified_figures     # the claim's number, absent from the prose
