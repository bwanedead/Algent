"""
What the trading agent is told and how it answers. The role is doctrine (the judgement), the schema is flat (one list of decision rows; the
provider rejects oneOf/anyOf), and the renderers turn a day's markets and the book's state into the task text. No limit is *enforced* here:
``guards.py`` clips whatever the agent asks; the role only says what the limits are so it does not waste its judgement on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from . import flags
from .book import Holding, side_price

PROMPT_VERSION = "trader-v1"
PROMPT_VERSION_RESEARCH = "trader-v2"

ROLE = """\
You run a paper-money portfolio on prediction markets for an intelligence desk. Nothing here is real money; what matters is that your decisions
are honest and that the record of them can be judged. Each day you are shown a batch of yes/no markets and, for every one: the question and its
exact resolution rules, the desk's own probability (made independently, without looking at the market's price), the market's price now and its
recent path, the days left, what the desk knows, and what you currently hold. You decide, per market: buy_yes, buy_no, sell, or hold.

How to think:
- The market price is a crowd's probability; the desk's number is an independent one. A gap is a reason to LOOK, not to trade. Ask why the
  crowd could be right and we wrong (information we lack, the rules read differently, a thin or stale market) before asking why we are right.
  If you cannot say what the crowd is missing, hold.
- Holding is the default and a fine answer. Most days most markets deserve no action. Do not trade to look busy. Every fill pays about a point
  of slippage, so a gap smaller than a few points is not an edge.
- Time matters. Money in a market that resolves in eight months is money not available for sooner, clearer chances; a market ending in days
  leaves little room to be wrong or to be proven right slowly. Short, well-evidenced gaps beat long, vague ones.
- Size by conviction and by how well the evidence supports it, not by the size of the gap alone. A small stake is the honest way to act on a
  hunch; a large one needs the rules read carefully and real evidence. You may add to a position you already hold when the reasons have
  strengthened, never merely because the price moved against it.
- Selling: close or reduce when the reason you bought is gone or has been used up (the price reached our value), when new evidence broke it, or
  when the money is better used elsewhere. Do not sell just because the position is down; do not hold just because it is up.
- To bet against an outcome, buy the other side (buy_no on a market you think is overpriced). You cannot hold both sides of one market.
- stake_usd: for a buy, the paper dollars to spend; for a sell, the dollars of current value to sell (give the full current value to close the
  whole position). For a hold use 0.
- The book has hard limits that are enforced for you: about {pos_frac:.0%} of the bankroll in any one market, {exp_frac:.0%} in total, never more
  cash than you have, nothing below a ${ticket:.0f} ticket. Asking for more than allowed simply gets cut, so do not spend thought on the limit;
  spend it on whether to act at all.
- The rationale is for a reader who is watching your results: one or two plain sentences saying why, in everyday words. Name the thing you
  think the crowd is getting wrong, or why you are standing aside. No jargon, no mention of these instructions, no hedging filler.
- Answer for every market shown, using its label (M1, M2, ...), exactly once.
""".format(pos_frac=flags.MAX_POSITION_FRAC, exp_frac=flags.MAX_EXPOSURE_FRAC, ticket=flags.TRADE_MIN_TICKET)


RESEARCH_ADDENDUM = """
Where "what the desk knows" comes from. It is what the desk's own corpus returned for queries planned for these markets: dated documents, claims,
events and entities, each with a bracketed id. Nothing outside the corpus is available. For each market, cite in `cited` the ids you actually
leaned on, and say in `evidence` how well they served you: "sufficient", "thin" or "gap". If a market is thin or a gap and the missing piece would
change your mind, name it in `gap_topic` (one specific thing the desk's research could look into: a person, event, document or figure) and what you
would do with it in `gap_why`. Thin evidence is a reason to hold or size small, not a reason to trust the crowd or the desk's number blindly.
"""

FAST_ADDENDUM = """
This is the FAST book. Only markets that settle within days are shown, and you are asked again every few hours, so the same market comes back with
a newer price and newer evidence. Resolution is close: a position taken here is judged within days, so favour clear, well-evidenced gaps and do not
sit in markets whose answer is already priced in by the rules and the calendar. Nothing is urgent; holding is still the default.
"""


class TraderCall(BaseModel):
    market: str = Field(description="The market's label exactly as shown, e.g. M3.")
    action: Literal["buy_yes", "buy_no", "sell", "hold"] = Field(description="buy_yes, buy_no, sell (close or reduce what you hold) or hold.")
    stake_usd: float = Field(default=0.0, description="Paper dollars: to spend on a buy, or of current value to sell. 0 for a hold.")
    rationale: str = Field(description="One or two plain-English sentences a reader can follow: why you act, or why you stand aside.")
    cited: list[str] = Field(default_factory=list, description="Ids (bracketed, in 'what the desk knows') you leaned on for this market.")
    evidence: Literal["sufficient", "thin", "gap"] = Field(default="sufficient", description="How well the evidence served this market.")
    gap_topic: str = Field(default="", description="When thin or a gap and it matters: the one specific thing the desk should research next.")
    gap_why: str = Field(default="", description="What you would do with it.")


class TraderOut(BaseModel):
    decisions: list[TraderCall] = Field(description="One entry for each market shown.")


@dataclass
class Case:
    """Everything the agent is shown about one market, assembled by trader.py."""

    label: str
    market_id: str
    question: str
    event_title: str
    rules: str
    end_date: str
    days_left: int | None
    ours: float | None
    ours_made: str
    ours_why: str
    yes_price: float | None
    path: list[tuple[str, float]]
    held: Holding | None
    evidence: str
    forecast_id: str = ""
    ids: list[str] = field(default_factory=list)


def _pct(p: float | None) -> str:
    return "n/a" if p is None else f"{p * 100:.0f}%"


def render_case(c: Case) -> str:
    lines = [f"### {c.label}  {c.question}"]
    if c.event_title and c.event_title != c.question:
        lines.append(f"Part of: {c.event_title}")
    lines.append(f"Ends: {c.end_date[:10] or 'unspecified'}" + (f" ({c.days_left} days left)" if c.days_left is not None else ""))
    lines.append(f"Resolution rules: {' '.join(c.rules.split())[:700] or '(none given)'}")
    if c.ours is not None:
        lines.append(f"The desk's own probability of YES: {_pct(c.ours)} (made {c.ours_made}). Its reasoning: {' '.join(c.ours_why.split())[:420]}")
    else:
        lines.append("The desk has no current probability for this market (you hold a position in it).")
    if c.yes_price is not None:
        lines.append(f"Market now: YES {_pct(c.yes_price)} / NO {_pct(1 - c.yes_price)}")
    else:
        lines.append("Market now: no recent price on file, so nothing can be bought or sold.")
    if c.path:
        lines.append("Market YES price, daily: " + ", ".join(f"{d[5:]} {p * 100:.0f}%" for d, p in c.path))
    if c.held is not None and c.yes_price is not None:
        now = c.held.shares * side_price(c.yes_price, c.held.side)
        lines.append(f"YOU HOLD: {c.held.side.upper()}, {c.held.shares:.1f} shares bought at an average {c.held.entry * 100:.0f}c; "
                     f"cost ${c.held.cost:.0f}, worth ${now:.0f} now ({now - c.held.cost:+.0f}); since {c.held.opened_at[:10]}.")
    else:
        lines.append("You hold nothing in this market.")
    lines.append("What the desk knows:\n" + (c.evidence or "(nothing relevant)"))
    return "\n".join(lines)


def render_task(day: str, cases: list[Case], *, cash: float, equity: float, invested: float, n_open: int, fast: bool = False) -> str:
    room = max(0.0, flags.MAX_EXPOSURE_FRAC * flags.BANKROLL - invested)
    head = (f"TODAY: {day}\n\n" + ("BOOK: fast (markets settling within days, decided every few hours).\n\n" if fast else "") + f"YOUR BOOK: started with ${flags.BANKROLL:,.0f}; cash ${cash:,.0f}; {n_open} open positions costing ${invested:,.0f}; "
            f"worth ${equity:,.0f} in all ({equity - flags.BANKROLL:+,.0f} since the start). Room for new positions: ${room:,.0f}.\n\n")
    body = "\n\n".join(render_case(c) for c in cases)
    return head + body + "\n\nTASK: one decision for each market above, using its label."
