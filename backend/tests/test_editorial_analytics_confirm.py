"""The independent pass over claims the analytics worker contributed."""

from __future__ import annotations

from algent_backend.agent_system.agents.editorial import analytics_confirm as ac
from algent_backend.agent_system.agents.editorial.analytics_confirm_contracts import (
    AnalyticsConfirmReport,
    ClaimCheck,
)

_ANALYTICS = {"added_by_stage": ac.ANALYTICS_STAGE}


def _profile(**over):
    return {
        "id": "p1",
        "claim_ledger": [
            {"id": "clm_an_1", "text": "Exports 2019: 542.2bn", "status": "unconfirmed",
             "supported_by": ["src_an_1"], "provenance": _ANALYTICS},
            {"id": "clm_an_2", "text": "Exports 2020: 512.5bn", "status": "unconfirmed",
             "supported_by": ["src_an_1"], "provenance": _ANALYTICS},
            # a normal research claim — must never be touched by this pass
            {"id": "clm_r1", "text": "Officials met", "status": "confirmed",
             "provenance": {"added_by_stage": "research"}},
        ],
        "source_ledger": [{"id": "src_an_1", "url": "https://kita.net/x"}],
        **over,
    }


def test_only_unchecked_analytics_claims_are_picked_up() -> None:
    """A research-graded claim is not this pass's business, and neither is one already ruled on."""
    pending = ac.analytics_claims(_profile())
    assert [c["id"] for c in pending] == ["clm_an_1", "clm_an_2"]

    already = _profile()
    already["claim_ledger"][0]["status"] = "confirmed"
    assert [c["id"] for c in ac.analytics_claims(already)] == ["clm_an_2"]


def test_verdicts_are_written_back_and_contested_is_reported() -> None:
    report = AnalyticsConfirmReport(checks=[
        ClaimCheck(claim_id="clm_an_1", verdict="confirmed", reason="matches the agency series",
                   checked_against=["https://kostat.go.kr/series"]),
        ClaimCheck(claim_id="clm_an_2", verdict="contested", reason="agency gives a fiscal year",
                   checked_against=["https://kostat.go.kr/series"], source_value="498.0bn"),
    ])
    out, contested = ac._apply(_profile(), report)
    by_id = {c["id"]: c for c in out["claim_ledger"]}

    assert by_id["clm_an_1"]["status"] == "confirmed"
    assert by_id["clm_an_2"]["status"] == "contested"
    # The disagreeing value rides along, because the chart drawn from this number is already
    # on the page and the next stage needs to know whether it can be repaired.
    assert "498.0bn" in by_id["clm_an_2"]["note"]
    assert contested == ["clm_an_2"]
    # The research-graded claim is untouched.
    assert by_id["clm_r1"]["status"] == "confirmed"


def test_confirmed_without_a_source_is_demoted_not_trusted() -> None:
    """`confirmed` is the one word in the ledger a reader is entitled to lean on.

    The model is asked to list what it consulted. When it claims confirmation and lists nothing,
    the honest record is that nothing independent was seen — accepting it would put the least
    evidence behind the strongest word.
    """
    report = AnalyticsConfirmReport(checks=[
        ClaimCheck(claim_id="clm_an_1", verdict="confirmed", reason="looks right"),
    ])
    out, contested = ac._apply(_profile(), report)
    by_id = {c["id"]: c for c in out["claim_ledger"]}

    assert by_id["clm_an_1"]["status"] == "unconfirmed"
    assert contested == []


def test_a_verdict_for_an_unrelated_claim_cannot_rewrite_it() -> None:
    """Only the ids handed to the pass are in its remit."""
    report = AnalyticsConfirmReport(checks=[
        ClaimCheck(claim_id="clm_r1", verdict="contested", reason="disagree",
                   checked_against=["https://x.test"]),
    ])
    pending_ids = {c["id"] for c in ac.analytics_claims(_profile())}
    kept = [c for c in report.checks if c.claim_id in pending_ids]
    assert kept == []


def test_nothing_contributed_means_no_pass_and_no_cost() -> None:
    clean = {"id": "p1", "claim_ledger": [
        {"id": "clm_r1", "text": "x", "status": "confirmed",
         "provenance": {"added_by_stage": "research"}}]}
    profile, report = ac.confirm_analytics_claims(None, None, clean)  # type: ignore[arg-type]
    assert profile is clean and report is None
