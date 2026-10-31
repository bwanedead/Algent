"""The mutation proposer: diagnosis from stored facts, free one-change children, and the single capped paid prompt draft (stubbed model, temp stores)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from algent_backend.experiment import flags, genealogy, mutate, policies, store
from algent_backend.experiment.contracts import Question, Resolution, RunRecord

T0 = datetime(2026, 1, 1, 12, tzinfo=UTC)
LEANING = [(0.08, 1 if i % 20 < 11 else 0) for i in range(20)]            # says 8%, happens 55%: the production-research lean


@pytest.fixture(autouse=True)
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))


def seed(pid: str, items: list[tuple[float, int]]) -> None:
    for i, (p, o) in enumerate(items):
        qid = f"q{i:03d}"
        end = (T0 + timedelta(days=i + 2)).isoformat(timespec="seconds")
        store.write_once(f"questions/{qid}.json", Question(id=qid, text=f"Will unique thing {qid} happen?", cutoff=(T0 + timedelta(days=i)).isoformat(timespec="seconds"), closes_at=end,
                                                           source=f"market:{qid}", reference={"market_p": 0.3}))
        store.write_once(f"resolutions/{qid}.json", Resolution(question_id=qid, outcome="yes" if o else "no", rule="t", resolved_at=end, recorded_at=end))
        rid = f"r-{qid}"
        store.write_once(f"runs/{rid}/run.json", RunRecord(run_id=rid, question_id=qid, protocol_id=pid, branch_id="b", snapshot="s", manifest_digest="m", prompt_digest="p",
                                                           output_digest="o", p=p))


class Drafter:
    def __init__(self, text: str, usd: float = 0.012):
        self.text, self.usd, self.tasks = text, usd, []

    def __call__(self, task: str, role: str):
        self.tasks.append((task, role))
        return SimpleNamespace(addendum=self.text, reasoning="addresses the lean"), self.usd


GOOD = ("Persistence is the default only until the window is long enough to hold a change; before settling low, ask how often a window this long, for this kind of question, "
        "actually contains one, because forecasting no change every time feels safe and is wrong whenever things move.")


def test_the_diagnosis_names_the_measured_lean_from_the_stored_calibration_table():
    p0 = policies.freeze_blind_forecaster()
    seed(p0.id, LEANING)
    d = mutate.diagnose(p0.id)
    assert d["n_forecasts"] == 20 and d["bias"] == {"status-quo bias": 20} and d["top"] == "status-quo bias" == d["top_prompt"]
    assert d["calibration"][0]["mean_p"] == pytest.approx(0.08) and d["calibration"][0]["hit_rate"] == pytest.approx(0.55)
    honest = policies.make("model", "m", 1, {"x": 1})
    assert mutate.diagnose(policies.compose("other", [honest]).id)["top"] == ""                    # nothing measured, nothing blamed


def test_free_children_each_change_one_policy_name_the_parent_and_put_calibration_first_for_a_lean():
    p0 = policies.freeze_blind_forecaster()
    seed(p0.id, LEANING)
    out = mutate.propose("p0")
    free = out["free"]
    assert free[0]["kind"] == "calibration" and {c["kind"] for c in free} == {"calibration", "evidence", "evidence-size"}
    assert len({c["protocol"] for c in free}) == len(free)
    for c in free:
        kid = policies.load_protocol(c["protocol"])
        assert kid.parent == p0.id and len(genealogy.changed(kid, p0)) == 1 and c["changed"] == genealogy.changed(kid, p0) and c["cost_usd"] == 0.0
    cal = {c["spec"].split("=")[1]: c for c in free if c["kind"] == "calibration"}
    assert set(cal) == {"platt", "platt-live", "identity"} or set(cal) == {"platt", "platt-live"}
    assert cal["platt"]["expect"]["n"] == 20 and cal["platt"]["expect"]["change_in_brier_minus_market"] is not None
    assert {c["spec"].split("=")[1] for c in free if c["kind"] == "evidence-size"} == {"4", "16"}
    assert any("keyword-overlap@1" in c["spec"] for c in free if c["kind"] == "evidence")
    assert "calibration" not in policies.load_protocol(p0.id).policies and "tournament" in out["next"]           # the parent is untouched
    assert out["paid"]["would_address"] == "status-quo bias" and out["paid"]["cap_usd"] == flags.MUTATE_CAP_USD and "--live" in out["paid"]["note"]
    assert "status-quo bias" in mutate.render(out)


def test_one_paid_draft_is_stored_as_a_new_prompt_version_and_the_old_one_is_never_edited():
    p0 = policies.freeze_blind_forecaster()
    seed(p0.id, LEANING)
    old_pv = p0.policies["prompts"]
    old_file = store.path(f"policies/{old_pv.digest}.json").read_text(encoding="utf-8")
    ask = Drafter(GOOD)
    out = mutate.propose("p0", ask=ask, live=True)["paid"]
    assert out["drafted"] and out["usd"] == pytest.approx(0.012) and out["tag"] == "status-quo bias"
    kid = policies.load_protocol(out["protocol"])
    new_pv = kid.policies["prompts"]
    assert new_pv.name == old_pv.name and new_pv.version == old_pv.version + 1 and new_pv.digest != old_pv.digest and kid.parent == p0.id
    assert new_pv.params["role"] == old_pv.params["role"] + "\n\n" + GOOD and new_pv.params["derived_from"] == old_pv.ref
    assert store.path(f"policies/{old_pv.digest}.json").read_text(encoding="utf-8") == old_file                 # never edited
    assert len(genealogy.changed(kid, p0)) == 1 and genealogy.changed(kid, p0)[0].startswith("prompts/blind-forecast@1 -> prompts/blind-forecast@2")
    assert len(ask.tasks) == 1
    again = mutate.propose("p0", ask=ask, live=True)["paid"]
    assert again["reused"] and len(ask.tasks) == 1 and again["protocol"] == out["protocol"]                       # a paid draft is never repeated


def test_the_drafter_is_told_the_measured_failure_and_the_doctrine_not_an_incident():
    p0 = policies.freeze_blind_forecaster()
    seed(p0.id, LEANING)
    ask = Drafter(GOOD)
    mutate.propose("p0", ask=ask, live=True)
    task, role = ask.tasks[0]
    assert "said about 8% -> happened 55% (n=20)" in task and p0.policies["prompts"].params["role"][:60] in task
    assert "unique thing" not in task                                                                             # no question text is pasted into the draft request
    for want in ("why it matters", "what going wrong looks like", "judgment", "do not invent numbers"):
        assert want in role.lower().replace("\n", " ")


def test_a_bad_draft_stores_no_policy_and_without_live_nothing_is_asked():
    p0 = policies.freeze_blind_forecaster()
    seed(p0.id, LEANING)
    n_policies = len(store.listing("policies"))
    bad = mutate.propose("p0", ask=Drafter("too short"), live=True)["paid"]
    assert not bad["drafted"] and "characters" in bad["reason"] and bad["usd"] > 0
    assert not any(c["kind"] == "prompts" for c in (store.read_json(f"policies/{f}") for f in store.listing("policies")) if c and c["version"] > 1)
    ask = Drafter(GOOD)
    mutate.propose("p0", ask=ask, live=False)
    assert ask.tasks == [] and len(store.listing("policies")) >= n_policies


def test_when_the_top_failure_is_retrieval_the_paid_step_declines_and_evidence_children_lead():
    p0 = policies.freeze_blind_forecaster()
    diag = {"protocol": p0.id, "n_forecasts": 9, "calibration": [], "bias": {}, "error_tags": {"retrieval miss": 6}, "top": "retrieval miss", "top_prompt": ""}
    assert mutate.propose_prompt(p0, diag, Drafter(GOOD))["drafted"] is False
    kinds = [c["kind"] for c in mutate.free_children(p0, diag)]
    assert kinds[0] == "evidence" and kinds.index("evidence") < kinds.index("calibration")
