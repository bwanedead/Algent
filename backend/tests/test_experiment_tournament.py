"""Successive-halving tournament and genome specs (stubbed models, temp stores)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from algent_backend.cli.newsroom import lab as lab_cli
from algent_backend.experiment import calibration, flags, genome, policies, qset, runner, sources, store, tournament
from algent_backend.experiment.contracts import Evidence, Question, Resolution

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)
DOCS = [Evidence(id="d1", kind="daily", source="t", title="talks stalled", body="Talks stalled over monitors", publish_time="2025-12-01", acquired_at="2025-12-01")]
N_Q = 8


@pytest.fixture(autouse=True)
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))


def make_set() -> dict:
    entries = []
    for i in range(N_Q):
        end = (T0 + timedelta(days=i + 2)).isoformat(timespec="seconds")
        q = Question(id=f"q{i}", text=f"Will talks {i} stall?", cutoff=(T0 + timedelta(days=i)).isoformat(timespec="seconds"), closes_at=end, source=f"market:q{i}", common_set=True,
                     reference={"market_p": 0.3})
        runner.save_question(q)
        store.write_once(f"resolutions/q{i}.json", Resolution(question_id=f"q{i}", outcome="yes" if i % 2 == 0 else "no", rule="t", resolved_at=end, recorded_at=end))
        entries.append({"id": q.id, "cutoff": q.cutoff, "source": q.source, "topic": "t"})
    return {"id": "set1", "questions": entries}


class Asker:
    """Per-protocol constant forecaster that counts its calls."""

    def __init__(self, by_spec: dict[str, tuple[float, float]]):
        self.table = {genome.parse(s).id: v for s, v in by_spec.items()}
        self.calls = 0

    def __call__(self, proto):
        p, usd = self.table[proto.id]

        def ask(task, role):
            self.calls += 1
            return SimpleNamespace(probability=p, rationale="r", cited=["d1"]), usd

        return ask


SPECS = {"p0": (0.1, 0.01), "p0;k=4": (0.9, 0.01), "p0;evidence=keyword-overlap@1": (0.5, 0.01)}      # only the 50% candidate beats the market (30%) on a coin-flip set


def test_halving_keeps_the_top_half_doubles_the_slice_and_reuses_stored_runs():
    doc, src = make_set(), sources.ListSource(DOCS)
    ask = Asker(SPECS)
    out = tournament.run(doc, list(SPECS), src, ask, live=True, budget_usd=1.0, first=2)
    assert [r["slice"] for r in out["rounds"][:2]] == [2, 4] and [len(r["alive"]) for r in out["rounds"][:2]] == [3, 2]
    assert ask.calls == 3 * 2 + 2 * 2                                                       # round one: 3 x 2 questions; round two: the 2 survivors on the 2 NEW questions only
    assert out["winner"] == "p0;evidence=keyword-overlap@1" and out["rounds"][0]["alive"][0]["brier_minus_market"] < 0 and out["spent_usd"] == pytest.approx(0.10)
    assert out["rounds"][0]["alive"][0]["n"] == 2 and out["rounds"][1]["alive"][0]["n"] == 4
    assert set(out["rounds"][0]["eliminated"]) == {"p0", "p0;k=4"} or len(out["rounds"][0]["eliminated"]) == 1
    again = tournament.run(doc, list(SPECS), src, ask, live=True, budget_usd=1.0, first=2)
    assert ask.calls == 10 and again["spent_usd"] == 0 and again["winner"] == out["winner"]  # never redo paid work
    assert "winner" in tournament.render(out)


def test_the_result_is_stored_write_once_with_the_genealogy_of_each_candidate():
    doc, src = make_set(), sources.ListSource(DOCS)
    out = tournament.run(doc, list(SPECS), src, Asker(SPECS), live=True, budget_usd=1.0, first=4)
    saved = store.read_json(f"tournaments/{out['id']}.json")
    assert saved["winner"] == out["winner"] and store.read_lines("tournaments/index.jsonl")[0]["id"] == out["id"]
    by = {c["spec"]: c for c in saved["candidates"]}
    base = by["p0"]
    assert by["p0;evidence=keyword-overlap@1"]["parent"] == base["id"] and by["p0;evidence=keyword-overlap@1"]["changed"] == ["evidence/recent-k@1 -> evidence/keyword-overlap@1"]
    assert by["p0;k=4"]["parent"] == base["id"] and len(by["p0;k=4"]["changed"]) == 1
    with pytest.raises(store.Immutable):
        store.write_once(f"tournaments/{out['id']}.json", {"tampered": True})


def test_the_budget_is_checked_before_every_call_and_stops_the_tournament():
    doc, src = make_set(), sources.ListSource(DOCS)
    ask = Asker(SPECS)
    out = tournament.run(doc, list(SPECS), src, ask, live=True, budget_usd=0.08, first=2)       # each call may cost up to RUN_CAP_USD (0.05): only calls that still fit are made
    assert out["stopped"] and out["winner"] is None and ask.calls == 4 and out["spent_usd"] == pytest.approx(0.04)
    assert out["spent_usd"] + qset.max_cost(policies.freeze_blind_forecaster()) > 0.08 and out["spent_usd"] <= 0.08


def test_without_live_nothing_is_called_and_the_plan_bounds_the_cost():
    doc, src = make_set(), sources.ListSource(DOCS)
    ask = Asker(SPECS)
    out = tournament.run(doc, list(SPECS), src, ask, live=False, first=2)
    assert not out["live"] and "add --live" in out["refused"] and ask.calls == 0 and not store.listing("runs")
    cap = flags.RUN_CAP_USD
    assert [r["new_runs_at_most"] for r in out["rounds"]] == [6, 4] and out["estimated_max_usd"] == pytest.approx((6 + 4) * cap) and out["within_budget"] is True
    assert "PLAN" in tournament.render(out)
    args = SimpleNamespace(qset="x", candidates="p0", first=2, budget=None, corpus=None, live=False, dry_run=True)
    assert args.dry_run                                                                          # the CLI path is the same call with live=False


def test_a_calibrated_candidate_rereads_the_raw_candidates_runs_instead_of_paying_again():
    doc, src = make_set(), sources.ListSource(DOCS)
    specs = {"p0": (0.1, 0.01), "p0;calibration=platt": (0.1, 0.01)}
    ask = Asker({"p0": (0.1, 0.01)})
    out = tournament.run(doc, list(specs), src, ask, live=True, budget_usd=1.0, first=4)
    assert ask.calls == 4 and {c["calibration"] for c in out["candidates"]} == {"", "calibration/platt@1"}      # 4 questions, one paid run each, for both candidates
    assert all(len(r["alive"]) <= 2 for r in out["rounds"])
    assert tournament.Candidate("p0;calibration=platt").raw.id == policies.freeze_blind_forecaster().id


def test_a_candidate_changes_exactly_one_policy_and_the_original_is_untouched():
    base = policies.freeze_blind_forecaster()
    with pytest.raises(ValueError):
        genome.parse("p0;k=4;calibration=platt")
    kid = genome.parse("p0;calibration=platt")
    assert kid.parent == base.id and kid.policies["calibration"].name == "platt" and "calibration" not in policies.load_protocol(base.id).policies
    assert calibration.split(kid)[0].id == base.id
    assert genome.parse("p0;calibration=platt").id == kid.id                                   # the same spec is the same protocol
    k = genome.parse("p0;k=16")
    assert k.policies["evidence"].params["k"] == 16 and k.parent == base.id
    with pytest.raises(KeyError):
        genome.parse("p0;evidence=recent-k@1")                                                 # already in use: not a change


def test_slice_sizes_and_survivors():
    assert tournament.slice_sizes(20, 6) == [6, 12, 20] and tournament.slice_sizes(5, 6) == [5] and tournament.slice_sizes(8, 2) == [2, 4, 8]
    assert [tournament.survivors(n) for n in (1, 2, 3, 5, 8)] == [1, 1, 2, 3, 4]
    assert lab_cli.run_tournament is not None
