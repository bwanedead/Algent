"""The spend envelope: a ceiling across runs that holds with nobody at the wheel."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from algent_backend.agent_system.foundation import spend_budget as sb


@pytest.fixture()
def env(tmp_path: Path, monkeypatch) -> Path:
    where = tmp_path / "budget.json"
    monkeypatch.setenv("ALGENT_SPEND_BUDGET", str(where))
    return where


def test_no_envelope_changes_nothing(env) -> None:
    assert sb.claim("r1") is None


def test_a_run_is_capped_at_what_the_envelope_has_left(env) -> None:
    sb.open_envelope(5.0, 5)
    assert sb.claim("r1") == 5.0
    sb.settle("r1", 0.8)
    assert sb.claim("r2") == pytest.approx(4.2)


def test_the_run_count_is_a_hard_stop(env) -> None:
    sb.open_envelope(5.0, 2)
    for rid in ("r1", "r2"):
        sb.claim(rid); sb.settle(rid, 0.1)
    with pytest.raises(sb.BudgetExhausted):
        sb.claim("r3")


def test_the_dollar_limit_is_a_hard_stop(env) -> None:
    sb.open_envelope(1.0, 5)
    sb.claim("r1"); sb.settle("r1", 1.0)
    with pytest.raises(sb.BudgetExhausted):
        sb.claim("r2")
    assert sb.runs_used(sb.load()) == 1          # the refused run never became a run


def test_a_run_that_dies_unsettled_keeps_its_whole_reservation(env) -> None:
    # A crash must never free money that may already have been spent.
    sb.open_envelope(5.0, 5)
    sb.claim("crashed")                           # reserves all $5, never settles
    with pytest.raises(sb.BudgetExhausted):
        sb.claim("next")


def test_a_dead_run_with_a_report_is_settled_from_it(env, tmp_path) -> None:
    sb.open_envelope(5.0, 5)
    sb.claim("abc")
    rep = tmp_path / "rails" / "0099__abc" / "artifacts"
    rep.mkdir(parents=True)
    (rep / "newsroom_rail_report.json").write_text(json.dumps({"total_usd": 0.6}))
    assert sb.reconcile(runs_root=tmp_path / "rails") == 1
    assert sb.committed(sb.load()) == pytest.approx(0.6)


def test_resume_reuses_its_slot(env) -> None:
    sb.open_envelope(5.0, 1)
    sb.claim("r1")
    assert sb.claim("r1") == 5.0                  # same article resumed, not a second run


def test_menus_spend_dollars_but_not_run_slots(env) -> None:
    sb.open_envelope(5.0, 1)
    sb.claim("menu:1", kind="menu"); sb.settle("menu:1", 0.02)
    assert sb.claim("r1") == pytest.approx(4.98)


def test_the_rail_refuses_before_spending_when_the_envelope_is_empty(env, monkeypatch) -> None:
    from algent_backend.agent_system.agents.newsroom import rail as rl
    from algent_backend.agent_system.runs.context import AgentRunContext

    sb.open_envelope(0.5, 5)
    sb.claim("old"); sb.settle("old", 0.5)
    ran: list = []
    monkeypatch.setattr(rl, "_run_rail", lambda *a, **k: ran.append(1) or {"rail": {}})
    ctx = AgentRunContext(run_id="t", model_resolver=object(), emit=lambda *a, **k: None)
    out = rl.build_newsroom_rail_graph(ctx).invoke({"pool": {"items": []}})
    assert ran == [] and out["rail"]["stage_reached"] == "refused"
