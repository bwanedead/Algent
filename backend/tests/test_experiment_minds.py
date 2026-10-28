"""Strict probabilities in the lab, the prior and delineation minds, the market-aware second output, and genealogy (stubbed models, temp stores)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from algent_backend.experiment import branches, controls, genealogy, minds, qset, runner, score, sources, store
from algent_backend.experiment.contracts import Evidence, Question
from algent_backend.markets import research as rs

CUTOFF = "2026-03-10T12:00:00+00:00"
Q = Question(id="q1", text="Will Aldoria and Brevia sign a ceasefire by 2026-03-31?", rules="Resolves YES if signed.", cutoff=CUTOFF, closes_at="2026-03-31T00:00:00+00:00",
             source="market:m1", reference={"market_p": 0.4})
DOCS = [Evidence(id="d-old", kind="daily", source="t", title="talks", body="Talks stalled", publish_time="2026-03-01", event_time="2026-03-01", acquired_at="2026-03-01")]


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGENT_EXPERIMENT_STORE", str(tmp_path / "lab"))
    monkeypatch.setenv("ALGENT_MARKETS_STORE", str(tmp_path / "markets"))
    monkeypatch.setenv("ALGENT_ACQUISITION_STORE", str(tmp_path / "acq"))


class Corpus:
    def search(self, text, *, kinds=None, since="", until="", limit=20):
        return [{"id": "d-old", "kind": "daily", "type": "document", "title": "talks", "date": "2026-03-01", "snippet": "talks stalled", "score": 3.0}]

    def entity(self, ref):
        return None


def run_one(proto, out):
    b = branches.ensure("x", proto)
    (rec,) = runner.run_controlled(Q, [b], sources.ListSource(DOCS), lambda p: (lambda t, r: (out, 0.01)), plan_ask_for=lambda pv: (lambda t, r: (SimpleNamespace(queries=[]), 0.0)),
                                   corpus=Corpus())
    return rec


def test_an_invalid_probability_is_a_visible_failure_row_in_the_lab():
    p0 = policies_p0()
    rec = run_one(p0, SimpleNamespace(probability_pct=0.07, rationale="r", cited=[]))
    assert rec.p is None                                                        # not rescaled to 7% or 0.07%: refused
    (row,) = store.read_lines("failures.jsonl")
    assert row["run"] == rec.run_id and row["raw"] == "0.07" and "whole number" in row["reason"]
    assert store.read_json(f"runs/{rec.run_id}/output.json")["invalid_reason"]


def policies_p0():
    from algent_backend.experiment import policies

    return policies.freeze_blind_forecaster()


def prior_out(**kw):
    base = dict(reference_class="ceasefires signed within a month", base_rate_pct=15, base_rate_basis="rough judgement", moved_by="nothing relevant", probability_pct=15,
                rationale="stays at the base rate", cited=[], evidence="gap", gap_topic="", gap_why="")
    return SimpleNamespace(**(base | kw))


def test_prior_variant_changes_only_the_prompt_and_stores_the_stated_base_rate():
    p0b = controls.freeze_production_research()
    prior = minds.freeze_prior()
    assert prior.parent == p0b.id and minds.freeze_prior().id == prior.id
    assert [c for c in genealogy.changed(prior, p0b)] == [f"{p0b.policies['prompts'].ref} -> {prior.policies['prompts'].ref}"]
    for kind in ("evidence", "model", "prediction", "memory", "tools"):          # everything else is the control's, digest for digest
        assert prior.policies[kind].digest == p0b.policies[kind].digest
    role, base = prior.policies["prompts"].params["role"], p0b.policies["prompts"].params["role"]
    assert role.startswith(base) and "BASE RATE FIRST" in role and "does not drift toward 50%" in role
    assert minds.schema_for(prior) is minds.PriorOut and list(minds.PriorOut.model_fields).index("base_rate_pct") < list(minds.PriorOut.model_fields).index("probability_pct")
    rec = run_one(prior, prior_out())
    out = store.read_json(f"runs/{rec.run_id}/output.json")
    assert rec.p == 0.15 and out["structured"]["reference_class"] == "ceasefires signed within a month" and out["structured"]["base_rate_pct"] == 15
    assert "base rate" in store.path(f"runs/{rec.run_id}/prompt.txt").read_text(encoding="utf-8")
    assert not runner.verify(rec.run_id)


def delineation_out(**kw):
    base = dict(proposition="A signed ceasefire agreement by 31 March", possibilities=[SimpleNamespace(id="H1", statement="signed", resolves="yes", prior_pct=20),
                                                                                    SimpleNamespace(id="H2", statement="talks drag on", resolves="no", prior_pct=80)],
                discriminators=[SimpleNamespace(observation="monitor deployment", favours="H1", why="needs both sides")],
                accounting=[SimpleNamespace(evidence_id="d-old", establishes="talks stalled", excludes_or_weakens="H1", assumptions=[SimpleNamespace(text="report is current", kind="soft")])],
                unmodelled=["a partial truce"], prior_pct=20, prior_moved="down: talks stalled", probability_pct=12, rationale="stalled", cited=["d-old"], evidence="thin",
                research_request="the text of the draft agreement")
    return SimpleNamespace(**(base | kw))


def test_delineation_changes_only_the_reasoning_and_stores_every_required_object():
    p0b = controls.freeze_production_research()
    b = minds.freeze_delineation()
    assert b.parent == p0b.id and minds.freeze_delineation().id == b.id
    assert b.policies["evidence"].digest == p0b.policies["evidence"].digest             # same evidence policy
    old, new = p0b.policies["model"], b.policies["model"]
    assert {k: v for k, v in new.params.items() if k not in ("max_tokens", "note")} == {k: v for k, v in old.params.items() if k != "max_tokens"}    # same model, effort, cap
    assert sorted(c.split(" -> ")[0].split("/")[0] for c in genealogy.changed(b, p0b)) == ["model", "prompts"]
    assert "game theory" not in b.policies["prompts"].params["role"].lower() and "worldview" not in b.policies["prompts"].params["role"].lower()
    fields = set(minds.DelineationOut.model_fields)
    assert {"proposition", "possibilities", "discriminators", "accounting", "unmodelled", "prior_pct", "prior_moved", "probability_pct", "research_request"} <= fields
    assert set(minds.Assumption.model_fields["kind"].annotation.__args__) == {"hard", "soft", "restructure"}
    rec = run_one(b, delineation_out())
    s = store.read_json(f"runs/{rec.run_id}/output.json")["structured"]
    assert rec.p == 0.12 and s["proposition"] and len(s["possibilities"]) == 2 and s["accounting"][0]["assumptions"][0]["kind"] == "soft" and s["research_request"]
    assert s["unmodelled"] == ["a partial truce"] and s["prior_pct"] == 20 and s["discriminators"][0]["favours"] == "H1"
    assert not runner.verify(rec.run_id)


def test_market_aware_estimate_is_stored_apart_and_scored_apart(monkeypatch):
    p0b = controls.freeze_production_research()
    rec = run_one(p0b, SimpleNamespace(probability_pct=10, rationale="low", cited=["d-old"]))
    seen = []

    def aware(task, role):
        seen.append(task)
        return SimpleNamespace(reasoning="the market knows more", probability_pct=30), 0.02

    doc = minds.run_aware(rec.run_id, Q, aware)
    assert doc["p"] == 0.3 and doc["independent_p"] == 0.1 and doc["market_p"] == 0.4 and "40%" in seen[0] and "40%" not in store.path(f"runs/{rec.run_id}/prompt.txt").read_text(encoding="utf-8")
    assert store.read_json(f"runs/{rec.run_id}/run.json")["p"] == 0.1                  # the independent forecast is untouched
    assert minds.run_aware(rec.run_id, Q, lambda t, r: 1 / 0) == doc                    # never redone
    store.write_once("resolutions/q1.json", {"question_id": "q1", "outcome": "no", "rule": score.RULE})
    board = score.scoreboard(resolve_now=False)["modes"]["controlled"]
    per = board["protocols"][p0b.id]["aware"]
    assert per["n"] == 1 and per["independent_minus_market"] < 0 < per["aware_minus_independent"]      # independent 10% beat the 40% market; the 30% aware estimate was worse
    assert board["rows"][0]["usd"] == pytest.approx(0.01 + 0.02 + 0.0)


def test_genealogy_names_parent_and_changes_and_abandoned_protocols_keep_their_results():
    p0 = policies_p0()
    p0b, prior, b = controls.freeze_production_research(), minds.freeze_prior(), minds.freeze_delineation()
    rec = run_one(prior, prior_out())
    nodes = {n["name"]: n for n in genealogy.tree()}
    assert nodes[p0.name]["depth"] == 0 and nodes["p0b-production-research-frozen"]["depth"] == 1 and nodes["p0b-prior"]["parent"] == p0b.id and nodes["b-delineation"]["depth"] == 2
    assert nodes["p0b-prior"]["changed"] and nodes["p0b-prior"]["runs"] == 1
    genealogy.retire("p0b-prior", "base rates were not better than the control")
    after = {n["name"]: n for n in genealogy.tree()}
    assert after["p0b-prior"]["retired"]["reason"].startswith("base rates") and after["p0b-prior"]["runs"] == 1       # abandoned: runs and evidence stay
    assert store.exists(f"runs/{rec.run_id}/manifest.json") and not runner.verify(rec.run_id) and b.id in {n["id"] for n in genealogy.tree()}
    text = genealogy.render(genealogy.tree())
    assert "ABANDONED" in text and "changed: prompts/blind-forecast@1 -> prompts/prior-forecast@1" in text


def test_named_protocols_resolve_for_the_set_runner():
    assert qset.protocol_named("p0b+prior").id == minds.freeze_prior().id and qset.protocol_named("b").id == minds.freeze_delineation().id
