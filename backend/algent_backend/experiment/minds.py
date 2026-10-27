"""
Independent forecasting minds (lab only). The lab's unit of experiment is a whole mind: its own research -> probability chain, never shown another protocol's
output or the market price before it commits (framework, "Production forecasting data flow"). The variants here change ONE thing relative to the frozen
production-research control P0b and say so in the genealogy (``genealogy.tree``):

  P0b+prior   a stated reference class and base rate first, then an evidence update (``prompts/prior-forecast@1``, schema ``prior``)
  B           delineation, alone: proposition, possibility set, discriminating evidence, evidence accounting, unmodelled possibilities, prior and its movement, one
              research request (``prompts/delineation@1``, schema ``delineation``). Same evidence policy as P0b; same model and effort (only the output ceiling is
              raised, ``model/house-low@2``, because the structured object is longer)

Every schema asks for ``probability_pct`` (a whole-number percent), read strictly by ``markets.forecast.read_probability``. A variant's role text is the FROZEN
P0b role plus an addendum, so nothing else about the instructions moves.

``run_aware`` adds the optional second output: after the independent estimate is stored, the same mind is shown the market price once and gives a market-aware
estimate, stored apart (``runs/<id>/aware.json``). The scoreboard keeps the two skills apart: independent skill vs mispricing detection.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from algent_backend.markets.forecast import ForecastOut, read_probability

from . import controls, policies, store
from .contracts import PolicyVersion, Protocol, Question

Verdict = Literal["sufficient", "thin", "gap"]
TASK_TAIL = "TASK: the probability this resolves YES, with a brief rationale and the evidence ids you used."


# ── schemas (field ORDER is the order the model writes them: the reasoning comes before the number) ───────────
class PriorOut(BaseModel):
    reference_class: str = Field(description="The kind of event this question is an instance of, over this much time and under rules like these (a short phrase).")
    base_rate_pct: float = Field(description="How often that kind of event happens, as a percentage from 0 to 100 (7 means 7%). Stated BEFORE you weigh the evidence.")
    base_rate_basis: str = Field(description="What the base rate rests on, in a sentence; say plainly if it is a rough judgement.")
    moved_by: str = Field(description="What moved you from the base rate and roughly how far, or that nothing did.")
    probability_pct: float = Field(description="Your final probability that the question resolves YES as a whole-number percentage from 0 to 100 (7 means 7%, never 0.07).")
    rationale: str = Field(description="Two to four sentences a reader can check.")
    cited: list[str] = Field(default_factory=list, description="Evidence ids (bracketed ids in the evidence) that bore on the answer.")
    evidence: Verdict = Field(default="sufficient", description="How well the evidence served this question.")
    gap_topic: str = Field(default="", description="When thin or a gap: the one specific thing to research next.")
    gap_why: str = Field(default="", description="What you would do with it.")


class Possibility(BaseModel):
    id: str = Field(description="A short label such as H1.")
    statement: str = Field(description="One way the world could turn out over the question's window, stated so that it settles the question one way.")
    resolves: Literal["yes", "no"] = Field(description="How the question's rules would settle if this possibility is what happens.")
    prior_pct: float = Field(description="Your probability for this possibility BEFORE the evidence, percent 0 to 100; the possibilities should sum to about 100.")


class Discriminator(BaseModel):
    observation: str = Field(description="An observation (existing or obtainable) that would separate the possibilities.")
    favours: str = Field(description="The id of the possibility it favours.")
    why: str = Field(description="Why that observation favours it over the others.")


class Assumption(BaseModel):
    text: str
    kind: Literal["hard", "soft", "restructure"] = Field(description="hard: taken as fixed, the analysis stands on it; soft: held loosely, revisable by one more observation; "
                                                                     "restructure: if it fails, the possibility set itself must be rebuilt.")


class AccountingEntry(BaseModel):
    evidence_id: str = Field(description="The bracketed id of one piece of evidence shown.")
    establishes: str = Field(description="What this observation establishes (empty if nothing).")
    excludes_or_weakens: str = Field(description="Which possibilities it excludes or weakens, by id (empty if none).")
    assumptions: list[Assumption] = Field(default_factory=list, description="What you had to assume to use it this way.")


class DelineationOut(BaseModel):
    proposition: str = Field(description="The precise proposition the rules settle, in your words, with what counts and what does not.")
    possibilities: list[Possibility] = Field(description="The possibility set: mutually exclusive ways the window could play out (typically 2 to 5).")
    discriminators: list[Discriminator] = Field(default_factory=list, description="Observations that would separate the possibilities and which each favours.")
    accounting: list[AccountingEntry] = Field(default_factory=list, description="One entry per piece of evidence you used.")
    unmodelled: list[str] = Field(default_factory=list, description="Ways the world could turn out that your possibility set does not cover.")
    prior_pct: float = Field(description="The probability of YES implied by your possibilities before the evidence, percent 0 to 100.")
    prior_moved: str = Field(description="How and why the evidence moved that prior (which entries, in which direction), or that it did not.")
    probability_pct: float = Field(description="Your final probability that the question resolves YES as a whole-number percentage from 0 to 100 (7 means 7%, never 0.07).")
    rationale: str = Field(description="Two to four sentences a reader can check.")
    cited: list[str] = Field(default_factory=list, description="Evidence ids that bore on the answer.")
    evidence: Verdict = Field(default="sufficient", description="How well the evidence served this question.")
    research_request: str = Field(default="", description="The ONE obtainable observation that would most change your estimate (a person, document, figure or event a researcher could fetch).")


class AwareOut(BaseModel):
    reasoning: str = Field(description="Whether the gap to the market's price is the market's error or something you could not see, in two or three sentences.")
    probability_pct: float = Field(description="Your final probability of YES as a whole-number percentage from 0 to 100.")


SCHEMAS: dict[str, type[BaseModel]] = {"forecast": ForecastOut, "prior": PriorOut, "delineation": DelineationOut, "aware": AwareOut}


def schema_for(proto: Protocol) -> type[BaseModel]:
    """The structured-output schema a protocol's prompt policy names (the frozen blind forecaster names none: ``ForecastOut``)."""
    return SCHEMAS[proto.policies["prompts"].params.get("schema", "forecast")]


# ── instructions (appended to the frozen P0b role; nothing in it is removed or reworded) ───────────────────
PRIOR_ADDENDUM = """

BASE RATE FIRST (a stated step that is stored with your answer). Before you weigh any evidence, name the reference class this question belongs to (the kind of event,
over this much time, under rules like these) and the base rate for that class as a percentage, with what it rests on; say so if it is a rough judgement. Then update
on the evidence. An update has to be earned: evidence that is thin, indirect or merely recent moves you little, and when nothing relevant was found your probability
stays at or very near the base rate you stated, wherever that is. It does not drift toward 50%. Say in `moved_by` what moved you and roughly how far, or that nothing
did. Write the final probability as a whole-number percentage."""

DELINEATION_ADDENDUM = """

DELINEATE BEFORE YOU FORECAST. Do not go straight to a number. Work through these steps and write them down in the fields asked for.
1. The precise proposition: what, exactly, the rules settle, and what would not count.
2. The possibility set: the mutually exclusive ways the window could play out, each marked by how the rules would settle it, each with a prior.
3. Discriminating evidence: which observations would separate the possibilities, and which possibility each favours and why.
4. Evidence accounting: for each piece of evidence you use, what it establishes and which possibilities it excludes or weakens, with the assumptions you had to make
   (hard: the analysis stands on it; soft: revisable by one more observation; restructure: if it fails, the possibility set must be rebuilt). Evidence you do not use
   needs no entry. An absence of evidence is not an observation unless you say why the observation would have been there.
5. What your possibility set does not cover.
6. The prior implied by the set, how the evidence moved it, and only then the final probability.
7. The one obtainable observation that would most change your estimate.
The same standards apply as above: read the rules literally, use the evidence for what it is, and be calibrated rather than cautious."""

AWARE_ROLE = """\
You are a forecaster on an intelligence desk. You already committed an independent probability for a question without seeing what any market thinks. You are now shown
the market's price at the same moment. A market can know things you do not, and it can also be wrong: thin, stale or crowd-driven. Decide whether the gap between
your number and the price is more likely your missing information or the market's error, and give your final probability. Do not average out of habit: move toward the
price only as far as you have reason to believe the market knows more than you, and stay where you are if you do not."""


def _variant(base: Protocol, name: str, prompts_name: str, addendum: str, tail: str, schema: str, version: str, extra: list[PolicyVersion] | None = None) -> Protocol:
    bp = base.policies["prompts"].params
    template = bp["task_template"]
    if TASK_TAIL not in template:
        raise ValueError("the frozen task template no longer ends in the expected TASK line; re-freeze before building a variant")
    prompts = policies.make("prompts", prompts_name, 1, {**bp, "prompt_version": version, "role": bp["role"] + addendum, "task_template": template.replace(TASK_TAIL, tail),
                                                         "schema": schema, "output_fields": list(SCHEMAS[schema].model_fields), "derived_from": base.policies["prompts"].ref})
    return policies.replace_policies(base, [prompts, *(extra or [])], name)


def _frozen(key: str, build: Callable[[], Protocol], note: str) -> Protocol:
    ptr = store.read_json(f"frozen/{key}.json")
    if ptr:
        return policies.load_protocol(ptr["protocol_id"])
    proto = build()
    store.write_once(f"frozen/{key}.json", {"protocol_id": proto.id, "parent": proto.parent, "captured_at": store.now_iso(), "note": note})
    return proto


def freeze_prior() -> Protocol:
    """P0b+prior: P0b with ONLY the prompt/schema changed to ask for a stated reference class and base rate first."""
    tail = ("TASK: first state the reference class and its base rate, then update on the evidence, then give the probability this resolves YES. "
            "Give the evidence ids you used.")
    return _frozen("p0b-prior", lambda: _variant(controls.freeze_production_research(), "p0b-prior", "prior-forecast", PRIOR_ADDENDUM, tail, "prior", "prior-v1"),
                   "P0b with a stated reference class and base rate before the evidence update; evidence policy and model identical")


def freeze_delineation() -> Protocol:
    """Protocol B: P0b with ONLY the reasoning changed to delineation. The model is the same house model and effort; the output ceiling is raised for the longer object."""
    def build() -> Protocol:
        p0b = controls.freeze_production_research()
        old = p0b.policies["model"]
        model = policies.make("model", old.name, old.version + 1, {**old.params, "max_tokens": 4096, "note": "same model, effort and temperature as P0b; output ceiling raised for the delineation object"})
        tail = "TASK: delineate the question as instructed, then give the probability this resolves YES and the one research request that would most change it."
        return _variant(p0b, "b-delineation", "delineation", DELINEATION_ADDENDUM, tail, "delineation", "delineation-v1", [model])

    return _frozen("b-delineation", build, "P0b with delineation as the only reasoning change; same evidence policy and model")


# ── the market-aware second output ─────────────────────────────────────────────────────────────────
AwareAsk = Callable[[str, str], tuple[Any, float]]


def aware_task(prompt: str, independent_p: float, rationale: str, market_p: float) -> str:
    return (f"{prompt}\n\nYOUR INDEPENDENT ESTIMATE (committed before you saw any price): {independent_p * 100:.0f}%\nYOUR REASONING THEN: {rationale}\n\n"
            f"THE MARKET'S PRICE FOR YES AT THIS MOMENT: {market_p * 100:.0f}%\n\nTASK: give your final probability this resolves YES.")


def live_aware_ask(proto: Protocol) -> AwareAsk:
    from algent_backend.markets import forecast as fc

    from . import flags

    m = proto.policies["model"].params
    return fc.default_ask(AWARE_ROLE, AwareOut, cap_usd=min(float(m["cap_usd"]), flags.RUN_CAP_USD), effort=m["effort"], max_tokens=1024)


def run_aware(rid: str, q: Question, ask: AwareAsk) -> dict[str, Any] | None:
    """The market-aware estimate of a stored run, written once beside the independent one. None when the run abstained or the question has no reference price.
    The independent forecast is never touched: both are scored, apart."""
    done = store.read_json(f"runs/{rid}/aware.json")
    if done:
        return done
    run, out = store.read_json(f"runs/{rid}/run.json"), store.read_json(f"runs/{rid}/output.json")
    mp = q.reference.get("market_p")
    if not run or not out or run.get("p") is None or mp is None:
        return None
    prompt = store.path(f"runs/{rid}/prompt.txt").read_text(encoding="utf-8")
    ans, usd = ask(aware_task(prompt, float(run["p"]), str(out.get("rationale", "")), float(mp)), AWARE_ROLE)
    frac, raw, why = read_probability(ans)
    pp = policies.load_protocol(run["protocol_id"]).policies["prediction"].params
    p = round(min(pp["p_max"], max(pp["p_min"], frac)), 4) if frac is not None else None
    doc = {"run": rid, "independent_p": run["p"], "market_p": mp, "p": p, "raw": raw, "invalid_reason": why, "reasoning": " ".join(str(getattr(ans, "reasoning", "")).split())[:600],
           "usd": round(float(usd or 0.0), 6), "at": store.now_iso()}
    store.write_once(f"runs/{rid}/aware.json", doc)
    if p is None:
        store.append("failures.jsonl", {"run": rid, "question": q.id, "stage": "aware", "raw": repr(raw)[:80], "reason": why, "usd": doc["usd"], "at": doc["at"]})
    return doc

