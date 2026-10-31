"""
Mutation proposer (``newsroom lab mutate PROTOCOL``): given a protocol's measured failures, propose children that each change exactly ONE policy and name the parent.

Reads two deterministic things, never a model's opinion: the cause tags of ``errors.breakdown`` (per question, over a set) and the protocol's calibration table (said vs
happened, from its stored runs). A lean the calibration table shows (``status-quo bias``: low forecasts that come true far more often than said; ``overclaiming yes``) is
a measured, quantified failure and outranks a count of per-question tags.

  free children (no model, no spend): swap the calibration policy (with the expected effect read off the stored runs by ``calibrate``), swap the evidence policy, halve or
      double the evidence size. They are ordered by how directly they answer the top failure.
  one paid child (``--live``, capped at ``flags.MUTATE_CAP_USD``): the house model drafts an ADDENDUM to the protocol's prompt that addresses the top prompt-addressable
      failure, stored as a NEW version of that prompt policy (the old version is never edited). The draft is asked for under doctrine-drafting ethos (why, failure
      mode, room for judgment, no invented thresholds, no incident pasted in). A draft is made once per (parent, failure): asking again returns the stored one.

Children are inert protocols until a tournament (``lab tournament``) or a run gives them evidence; nothing here runs a forecast.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from . import calibrate, calibration, errors, flags, genome, policies, store
from .contracts import Protocol

#: tags a prompt can plausibly address (retrieval and leakage tags are about evidence and the replay, not the mind's instructions)
PROMPT_TAGS = ("status-quo bias", "overclaiming yes", "extreme/overconfident", "wrong base rate")
#: tags that point at the evidence policy
EVIDENCE_TAGS = ("retrieval miss", "out-of-coverage")

BRIEFS = {
    "status-quo bias": "Its low probabilities come true far more often than it says: it treats the present state persisting as the default and undercounts how often a window of this length contains a change.",
    "overclaiming yes": "Its high probabilities fail more often than it says: it reads a live possibility as a likely event and rounds momentum up into certainty.",
    "extreme/overconfident": "It commits to the far ends (very high or very low) and is on the wrong side of the outcome often enough to be costly.",
    "wrong base rate": "It states a base rate on the wrong side of what usually happens for this kind of question, and then stays near it.",
}

DRAFT_ROLE = """\
You revise the standing instructions of a forecasting mind. You are given one measured, recurring failure of that mind (seen across many resolved questions, not one
incident) and the instructions it runs under today. Write ONE short paragraph, under 150 words, to append to those instructions so that the failure stops recurring.

Write it as doctrine, not a rule list. Say what to do, why it matters, and what going wrong looks like, so the forecaster can generalise to a question you never saw.
Keep room for judgment (phrases like "when the evidence supports it", "if nothing in the evidence bears on it"). Avoid always and never, and do not invent numbers or
thresholds: a number you make up becomes a ceiling the mind obeys instead of a thing it understands. Do not paste in any question, name or incident; the paragraph has
to still be right on the next hundred questions. Do not repeat what the current instructions already teach; where they already cover part of it, strengthen the reason
instead of restating the rule. Do not change the output format, the probability scale, the tools or the evidence handling."""


class AddendumOut(BaseModel):
    addendum: str = Field(description="One paragraph (under 150 words) to append to the forecaster's instructions, written as doctrine: what to do, why, and what going wrong looks like.")
    reasoning: str = Field(default="", description="One sentence on how this addresses the measured failure.")


def diagnose(pid: str, doc: dict[str, Any] | None = None, *, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The protocol's measured failures: calibration bins and the leans they show, per-question error tags over the set (if given), and the top failure."""
    mine = [r for r in (calibrate.lab_rows() if rows is None else rows) if r["protocol"] == pid and r["p"] is not None]
    bins = calibrate.bins([(r["p"], r["o"]) for r in mine])
    bias: dict[str, int] = {}
    for b in bins:
        gap = b["hit_rate"] - b["mean_p"]
        if b["n"] >= flags.MUTATE_BIAS_MIN_N and gap >= flags.MUTATE_BIAS_GAP and b["mean_p"] < 0.5:
            bias["status-quo bias"] = bias.get("status-quo bias", 0) + b["n"]
        elif b["n"] >= flags.MUTATE_BIAS_MIN_N and -gap >= flags.MUTATE_BIAS_GAP and b["mean_p"] > 0.5:
            bias["overclaiming yes"] = bias.get("overclaiming yes", 0) + b["n"]
    tags: dict[str, int] = {}
    if doc is not None:
        for r in errors.breakdown(doc)["rows"]:
            if r["protocol"] == pid:
                for t in [x.strip() for x in r["tag"].split(";") if x.strip()]:
                    tags[t] = tags.get(t, 0) + 1
    ranked = sorted(bias.items(), key=lambda kv: (-kv[1], kv[0])) + sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))
    return {"protocol": pid, "n_forecasts": len(mine), "calibration": bins, "bias": bias, "error_tags": tags, "top": ranked[0][0] if ranked else "",
            "top_prompt": next((t for t, _ in ranked if t in PROMPT_TAGS), "")}


def _why(tag: str, kind: str, change: str) -> str:
    if kind == "calibration":
        return f"{change}: answers {tag or 'any systematic lean'} directly by correcting the probability after the mind commits; free to score on stored runs"
    if kind == "evidence":
        return f"{change}: tests whether the evidence the mind sees is the limit" + (f" (top failure: {tag})" if tag else "")
    return f"{change}: tests whether the amount of evidence shown matters" + (f" (top failure: {tag})" if tag else "")


def free_children(proto: Protocol, diag: dict[str, Any], board: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every one-change child that needs no model: calibration swaps, evidence swaps, evidence size. Ordered by how directly each answers the top failure."""
    top = diag.get("top", "")
    cal_now = proto.policies["calibration"].name if "calibration" in proto.policies else "identity"
    by_cal = ((board or {}).get("protocols", {}).get(calibration.base_id(proto), {}) or {}).get("policies", {})
    out = []
    for name in ("platt", "platt-live", "identity"):
        if name == cal_now:
            continue
        kid = genome.with_calibration(proto, name)
        est = by_cal.get(name)
        out.append({"kind": "calibration", "protocol": kid.id, "name": kid.name, "spec": f"{proto.id};calibration={name}", "changed": genome.describe(kid)["changed"],
                    "expect": None if not est else {"change_in_brier_minus_market": est["change_in_brier_minus_market"], "n": est["n"], "n_fitted": est["n_fitted"]},
                    "why": _why(top, "calibration", f"calibration {cal_now} -> {name}"), "cost_usd": 0.0})
    for alt in genome.evidence_alternatives(proto):
        kid = genome.with_evidence(proto, alt.ref.split("/", 1)[1])
        out.append({"kind": "evidence", "protocol": kid.id, "name": kid.name, "spec": f"{proto.id};evidence={alt.name}@{alt.version}", "changed": genome.describe(kid)["changed"],
                    "expect": None, "why": _why(top, "evidence", f"evidence {proto.policies['evidence'].ref} -> {alt.ref}"), "cost_usd": 0.0})
    for k, _ in genome.k_variants(proto):
        kid = genome.with_k(proto, k)
        out.append({"kind": "evidence-size", "protocol": kid.id, "name": kid.name, "spec": f"{proto.id};k={k}", "changed": genome.describe(kid)["changed"], "expect": None,
                    "why": _why(top, "size", f"evidence size -> {k}"), "cost_usd": 0.0})
    lean = top in PROMPT_TAGS
    rank = {"calibration": 0 if lean else 2, "evidence": 0 if top in EVIDENCE_TAGS else 1, "evidence-size": 1 if top in EVIDENCE_TAGS else 3}
    out.sort(key=lambda c: (rank[c["kind"]], c["expect"]["change_in_brier_minus_market"] if c["expect"] and c["expect"]["change_in_brier_minus_market"] is not None else 0.0))
    return out


# ── the one paid child: a drafted prompt addendum, stored as a NEW prompt version ─────────────────────
def next_prompt_version(name: str) -> int:
    best = 0
    for f in store.listing("policies"):
        raw = store.read_json(f"policies/{f}")
        if raw and raw.get("kind") == "prompts" and raw.get("name") == name:
            best = max(best, int(raw.get("version", 0)))
    return best + 1


def _facts(diag: dict[str, Any], tag: str) -> str:
    if tag in diag["bias"]:
        rows = [b for b in diag["calibration"] if b["n"] >= flags.MUTATE_BIAS_MIN_N]
        table = "; ".join(f"said about {round(b['mean_p'] * 100)}% -> happened {round(b['hit_rate'] * 100)}% (n={b['n']})" for b in rows)
        return f"Across {diag['n_forecasts']} resolved forecasts: {table}."
    return f"Tagged on {diag['error_tags'].get(tag, 0)} of {diag['n_forecasts']} resolved forecasts."


def propose_prompt(proto: Protocol, diag: dict[str, Any], ask: Any) -> dict[str, Any]:
    """Draft (once per parent and failure) an addendum for the prompt policy and store it as a new version; returns the record. ``ask`` is (task, role) -> (AddendumOut, usd)."""
    tag = diag["top_prompt"]
    if not tag:
        return {"drafted": False, "reason": "no prompt-addressable failure measured (the top failure, if any, is about evidence or replay)"}
    mid = store.digest([proto.id, tag])[:12]
    done = store.read_json(f"mutations/{mid}.json")
    if done:
        return {**done, "reused": True}
    pv = proto.policies["prompts"]
    task = (f"MEASURED FAILURE: {BRIEFS[tag]}\nEVIDENCE FOR IT: {_facts(diag, tag)}\n\nCURRENT INSTRUCTIONS THE MIND RUNS UNDER:\n{pv.params['role']}\n\n"
            "TASK: write the one paragraph to append.")
    ans, usd = ask(task, DRAFT_ROLE)
    text = " ".join(str(getattr(ans, "addendum", "") or "").split())
    if not 40 <= len(text) <= 1200:
        rec = {"id": mid, "parent": proto.id, "tag": tag, "drafted": False, "reason": f"the draft was {len(text)} characters (wanted 40 to 1200); nothing stored as a policy", "usd": round(float(usd or 0), 6)}
        store.write_once(f"mutations/{mid}.json", rec)
        return rec
    version = next_prompt_version(pv.name)
    new = policies.make("prompts", pv.name, version, {**pv.params, "role": pv.params["role"] + "\n\n" + text, "prompt_version": f"{pv.params.get('prompt_version', pv.name)}+m{version}",
                                                     "derived_from": pv.ref, "mutation": {"tag": tag, "parent": proto.id}})
    kid = genome.child(proto, new, f"{proto.name}~{re.sub(r'[^a-z0-9]+', '-', tag.lower()).strip('-')}")
    rec = {"id": mid, "parent": proto.id, "tag": tag, "drafted": True, "protocol": kid.id, "name": kid.name, "spec": f"{kid.id}", "prompt": new.ref, "addendum": text,
           "reasoning": str(getattr(ans, "reasoning", ""))[:300], "usd": round(float(usd or 0), 6), "changed": genome.describe(kid)["changed"]}
    store.write_once(f"mutations/{mid}.json", rec)
    return rec


def live_draft_ask() -> Any:
    """The house model under the budget gate, capped at ``flags.MUTATE_CAP_USD``."""
    from algent_backend.markets import forecast as fc

    return fc.default_ask(DRAFT_ROLE, AddendumOut, cap_usd=flags.MUTATE_CAP_USD, effort="low", max_tokens=900)


def propose(ref: str, doc: dict[str, Any] | None = None, *, ask: Any = None, live: bool = False, board: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The full proposal for one protocol: diagnosis, free children, and (only with ``live``) the one paid prompt child."""
    proto = genome.load(ref)
    raw, _ = calibration.split(proto)
    rows = calibrate.lab_rows() if rows is None else rows
    diag = diagnose(raw.id, doc, rows=rows)
    board = board if board is not None else calibrate.lab_board(rows=rows, live=[])
    out: dict[str, Any] = {"parent": {"id": proto.id, "name": proto.name}, "diagnosis": diag, "free": free_children(proto, diag, board)}
    if live and ask is not None:
        out["paid"] = propose_prompt(proto, diag, ask)
    else:
        tag = diag["top_prompt"]
        out["paid"] = ({"drafted": False, "would_address": tag, "cap_usd": flags.MUTATE_CAP_USD, "note": "add --live to have the house model draft a prompt addendum for this failure"} if tag
                       else {"drafted": False, "reason": "no prompt-addressable failure measured"})
    out["next"] = "newsroom lab tournament --set latest --candidates " + ",".join([proto.id, *[c["spec"] for c in out["free"][:3]], *([out["paid"]["spec"]] if out["paid"].get("drafted") else [])])
    return out


def render(doc: dict[str, Any]) -> str:
    d = doc["diagnosis"]
    lines = [f"parent {doc['parent']['name']} ({doc['parent']['id'][:8]}): {d['n_forecasts']} resolved forecasts; top failure: {d['top'] or 'none measured'}"]
    lines += [f"  said {round(b['mean_p'] * 100):>3}% -> happened {round(b['hit_rate'] * 100):>3}%  (n={b['n']})" for b in d["calibration"]]
    for c in doc["free"]:
        e = c["expect"]
        lines.append(f"  free  {c['why']}" + ("" if not e or e["change_in_brier_minus_market"] is None else f"  [stored runs: {e['change_in_brier_minus_market']:+.3f} Brier vs market, {e['n_fitted']}/{e['n']} recalibrated]"))
    p = doc["paid"]
    lines.append("  paid  " + (f"drafted {p['prompt']} for '{p['tag']}' (${p['usd']:.3f}): {p['addendum'][:140]}..." if p.get("drafted") else p.get("note") or p.get("reason", "")))
    lines.append(doc["next"])
    return "\n".join(lines)
