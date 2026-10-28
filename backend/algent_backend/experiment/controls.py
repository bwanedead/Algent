"""
Frozen controls beyond the blind forecaster. Each ``freeze_*`` copies production AS IT IS NOW into the store once (a pointer under ``frozen/``) and later calls
return the stored capture, whatever the code says. A new freeze never edits an old one: it is a NEW protocol that names the one it supersedes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from algent_backend.markets import research as rs

from . import policies, store
from . import research_policy as rp
from .contracts import PolicyVersion, Protocol
from .cutoff_corpus import CutoffCorpus


def _research_impl() -> list[Callable[..., Any]]:
    return [rp.retrieve, rp._to_evidence, CutoffCorpus, rs.research, rs.run_query, rs._blocked]


def production_research_policy() -> PolicyVersion:
    return policies.make("evidence", rp.NAME, rp.VERSION, rp.captured_params(), _research_impl())


def freeze_production_research() -> Protocol:
    """P0b: the frozen blind forecaster with production's model-planned corpus research as its evidence policy (cutoff-bounded). Supersedes P0, which stays as it is."""
    ptr = store.read_json("frozen/p0-research.json")
    if ptr:
        return policies.load_protocol(ptr["protocol_id"])
    p0 = policies.freeze_blind_forecaster()
    proto = policies.replace_policy(p0, production_research_policy(), "p0b-production-research-frozen")
    store.write_once("frozen/p0-research.json", {"protocol_id": proto.id, "supersedes": p0.id, "captured_at": store.now_iso(), "from": "markets/research.py",
                                                 "note": "same prompt, model and bounds as P0; the evidence policy is production's planned corpus research over a cutoff-bounded view"})
    return proto


def impl_drift(proto: Protocol) -> dict[str, dict[str, str]]:
    """Evidence policies whose code changed since they were frozen: stored ``impl_sha`` vs the code now. Empty = the control still runs what it was captured with."""
    pv = proto.policies.get("evidence")
    if pv is None or not pv.impl_sha:
        return {}
    fns = _research_impl() if policies.is_planned(pv) else [policies.RETRIEVERS[(pv.name, pv.version)]]
    now = policies.sha_of(*fns)
    return {} if now == pv.impl_sha else {pv.ref: {"frozen": pv.impl_sha, "now": now}}


# ── the paper traders as controls ────────────────────────────────────────────────────────────────
def _trader_impl() -> list[Callable[..., Any]]:
    from algent_backend.markets import guards, trader_prompt

    return [trader_prompt.render_case, trader_prompt.render_task, guards.apply, guards._buy, guards._sell]


def impl_drift_decision(proto: Protocol) -> dict[str, dict[str, str]]:
    """The frozen trader's renderer/guards code vs what was pinned at the freeze (empty = unchanged)."""
    pv = proto.policies["decision"]
    now = policies.sha_of(*_trader_impl())
    return {} if now == pv.impl_sha else {pv.ref: {"frozen": pv.impl_sha, "now": now}}


def freeze_trader() -> Protocol:
    """The daily-book trader as it is now: role text, output fields, model settings and the book's guards. Replayable (``decision.replay``): the same market
    state and evidence at a cutoff, one structured call. The task renderer and the guards are code, pinned by ``impl_sha``."""
    ptr = store.read_json("frozen/trader.json")
    if ptr:
        return policies.load_protocol(ptr["protocol_id"])
    from algent_backend.markets import books, trader, trader_prompt
    from algent_backend.markets import flags as mf

    prompts = policies.make("prompts", "trader-role", 1, {"prompt_version": trader_prompt.PROMPT_VERSION_RESEARCH if mf.RESEARCH_ENABLED else trader_prompt.PROMPT_VERSION,
                                                          "role": trader.role_for("daily"), "output_fields": list(trader_prompt.TraderCall.model_fields), "book": "daily"})
    model = policies.make("model", "house-trader", 1, {"spec": "house", "effort": mf.TRADE_EFFORT, "max_tokens": 4096, "cap_usd": books.get("daily").call_cap_usd()})
    decision = policies.make("decision", "paper-guards", 1, {"bankroll": mf.BANKROLL, "max_position_frac": mf.MAX_POSITION_FRAC, "max_exposure_frac": mf.MAX_EXPOSURE_FRAC,
                                                             "min_ticket": mf.TRADE_MIN_TICKET, "slippage": mf.SLIPPAGE, "path_days": mf.TRADE_PATH_DAYS,
                                                             "evidence_chars": mf.TRADE_EVIDENCE_CHARS}, _trader_impl())
    prediction = policies.make("prediction", "desk-probability-plus-price", 1, {"consumes": "the desk's blind probability and the market's price", "actions": ["buy_yes", "buy_no", "sell", "hold"]})
    proto = policies.compose("trader-daily-frozen", [prompts, model, decision, prediction, policies.make("tools", "none", 1, {}), policies.make("memory", "none", 1, {"write": False}),
                                                     production_research_policy()])
    store.write_once("frozen/trader.json", {"protocol_id": proto.id, "captured_at": store.now_iso(), "from": "markets/trader.py + trader_prompt.py + guards.py", "replayable": True})
    return proto


def freeze_day_bot() -> Protocol:
    """The day book's agent as it is now: role, tool list and loop bounds, model settings, guards. FROZEN BUT NOT REPLAYABLE: it browses Polymarket live through
    tools over many turns, which cannot be presented as one fixed state at a past cutoff. The capture is the control for a later tool-capable replay harness."""
    ptr = store.read_json("frozen/day-bot.json")
    if ptr:
        return policies.load_protocol(ptr["protocol_id"])
    from algent_backend.markets import day_prompt, day_tools, guards
    from algent_backend.markets import flags as mf

    prompts = policies.make("prompts", "day-role", 1, {"prompt_version": day_prompt.PROMPT_VERSION, "role": day_prompt.role(), "turn_fields": list(day_prompt.Turn.model_fields),
                                                       "call_fields": list(day_prompt.Call.model_fields)})
    tools = policies.make("tools", "day-tools", 1, {"names": list(day_prompt.TOOLS), "max_turns": mf.DAY_MAX_TURNS, "max_tool_calls": mf.DAY_MAX_TOOL_CALLS,
                                                    "max_calls_per_turn": mf.DAY_MAX_CALLS_PER_TURN, "max_orders_per_run": mf.DAY_MAX_ORDERS_PER_RUN,
                                                    "result_chars": mf.DAY_RESULT_CHARS, "transcript_chars": mf.DAY_TRANSCRIPT_CHARS}, [day_tools.Session])
    model = policies.make("model", "house-day", 1, {"spec": "house", "effort": mf.DAY_EFFORT, "max_tokens": 2500, "cap_usd": mf.DAY_CALL_CAP_USD})
    decision = policies.make("decision", "paper-guards-day", 1, {"bankroll": mf.DAY_BANKROLL, "max_position_frac": mf.DAY_MAX_POSITION_FRAC, "max_exposure_frac": mf.DAY_MAX_EXPOSURE_FRAC,
                                                                 "min_ticket": mf.TRADE_MIN_TICKET, "slippage": mf.SLIPPAGE, "horizon_h": mf.DAY_HORIZON_H}, [guards.apply, guards._buy, guards._sell])
    prediction = policies.make("prediction", "p-yes-recorded-with-order", 1, {"consumes": "live market state through tools", "p_yes_given_with_each_order": True})
    proto = policies.compose("day-bot-frozen", [prompts, tools, model, decision, prediction, policies.make("memory", "watchlist", 1, {"persists_between_runs": True})])
    store.write_once("frozen/day-bot.json", {"protocol_id": proto.id, "captured_at": store.now_iso(), "from": "markets/day_prompt.py + day_tools.py + guards.py", "replayable": False,
                                             "why": "multi-turn live tool use against Polymarket cannot be presented as one fixed state at a past cutoff"})
    return proto
