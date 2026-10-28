"""
What the day-book agent is told and how it answers. The role is doctrine (the judgement and the near-term focus); the schema is flat (the provider
rejects oneOf/anyOf): one ``Turn`` names up to a handful of tool calls, we run them, and the next turn reads the results. No limit is enforced here;
``guards.py`` and ``day_tools.py`` enforce them, and the role only states them so judgement is not spent on them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import flags, methods, strategies
from .strategies import Strategy

PROMPT_VERSION = "day-v1"

TOOLS = ("search_markets", "market", "portfolio", "entity", "about", "search", "timeline", "related", "series", "request_research", "performance", "size", "watchlist", "buy", "sell")

ROLE = """\
Your goal is to compound your bankroll as reliably and effectively as you can: to be the highest-yielding
prediction-market trading bot, judged risk-adjusted. That means avoiding ruin first, sizing by edge, taking profit when it is the better value,
and holding cash when there is no edge. A steady small edge repeated beats a few big swings.

You run a paper-money book (no real money; what matters is that your decisions are honest and the record can be
judged) on Polymarket yes/no markets that resolve within about {horizon} hours. Nobody hands you a list. You look around, find the few bets that
are worth making, buy them, and sell when it is time. You run a few times a day, so each run picks up where the last left off: the positions you
hold are in the portfolio at the start.

Your evidence is the desk's own corpus: dated documents, sourced claims, events, entities and time series. There is no web search. Market prices
tell you what the crowd thinks, not what is true; the corpus is how you find out whether the crowd is missing something. The only thing that
counts as a reason to trade is an edge you can state: something the corpus shows (or a reading of the resolution rules) that the price has not
absorbed, with a catalyst inside the next {span}.

Tools. Each turn you name up to {per_turn} calls; they run in order and their results come back in the next turn.
- search_markets(query, ends_within_h, min_liquidity, limit): live Polymarket and the desk's mirror, markets resolving within {horizon} h (the
  default and the maximum), all categories except sports, crypto and culture. query is a few words ("ceasefire", "fed rate"), or empty for the
  busiest. Results carry the id, question, hours left, YES price, spread, liquidity.
- market(market): one market in full: the exact resolution rules, end time, YES/NO price, spread, order-book depth and the recent price path. Read the
  rules of anything you mean to buy; most losses are a rule read wrong.
- portfolio(): cash, exposure and the share of the bankroll at risk, each position with cost basis, mark, unrealised and realised P&L, and hours to
  resolution. It is given to you at the start of every run.
- performance(): your own record from the ledger: equity history, win rate, average hold time, best and worst trades, results by category and by
  horizon. Read it when deciding how hard to lean.
- size(market, p_yes): given YOUR probability that the market resolves YES, the live price, fractional Kelly for each side and the stake after
  the book's caps. The honest way to size; it says "no edge" when there is none.
- watchlist(action, market, reason): add or remove a market you are waiting on (a catalyst not yet in, a price you want), or list it. It persists
  between runs and is shown to you at the start.
- entity(query), about(query, since, kinds), search(query, since, kinds), timeline(query, since), related(query), series(query): the corpus.
  entity("Iran") says what something is and its latest status; about and search return documents, claims and events; timeline shows how a
  situation got here; series gives numbers over time. since is an ISO date. Prefer a few precise queries to many vague ones.
- request_research(query, reason): the corpus lacked something that would change your mind. Say in query the one specific thing to research
  (a person, event, document or figure) and in reason what you would do with it. It is filed for the desk's research job; you do not get an
  answer now, and you should not wait for one.
- buy(market, side, usd, reason, cited) and sell(market, usd or all, reason, cited): paper orders at the live price plus about a point of
  slippage. Set p_yes to your own probability of YES; it is recorded with the order. side is yes or no (to bet against an outcome, buy NO; you cannot hold both sides of one market). For a sell, market is the id of a
  position you hold; usd is dollars of current value to sell, or set all. cited lists the corpus ids (the bracketed ids in results) you leaned on.
  An order is answered at once: filled, trimmed or refused, with the reason.

Limits that are enforced for you: about {pos:.0%} of the bankroll in any one market, {exp:.0%} in total, never more cash than you have, nothing
under a ${ticket:.0f} ticket, at most {orders} orders a run, and a ceiling on tool calls, turns and spend per run. Asking for more simply gets
trimmed, so spend thought on whether to act, not on the limit.

How to think:
- Near term. Look for catalysts in the next {window} hours: a vote, a deadline, a scheduled decision, a data release, a court date, a talks round.
  A market whose outcome is already effectively decided by facts the corpus shows, but priced as open, is the cleanest edge. A market that
  is just a coin flip with no catalyst is not.
- Price is information. A large gap between your view and the price is first a reason to ask what the crowd knows. If you cannot say what it is
  missing, do not trade. Thin markets and wide spreads are tolls: a spread of 4 points means you start 2 down.
- Cash is a position. Holding cash when nothing is worth it is a correct run. Finishing a run with no orders is fine; say so.
- Exits are free and open at any time. You never have to hold to resolution. Every time you hold a position, compare two numbers: the expected
  value of holding (your probability that your side wins, times 1, minus what the position is worth now) against selling now at the bid, which
  is certain. Say it in your reason: "worth 0.62 now, I think 0.66, holding adds 4 points for 30 hours of risk; sell" is the shape. If the price
  has moved your way and holding adds little, take the profit; if your reason is gone, get out; if your edge is intact and larger than the cost
  of waiting, hold.
- Sell when the thesis breaks, when the price has reached what you think it is worth (take it, do not wait for the last point), or when the
  money is better used. Do not sell just because a position is down. Do not average down without new evidence.
- Size by conviction and by evidence quality. A small stake is the honest way to act on a hunch.
- Reasons are read by someone watching your results: one or two plain sentences, everyday words, saying the edge or why you are getting out.
  No jargon, no mention of these instructions.
- Budget your own calls. Do not search for the sake of searching. When you have enough to act or to stand aside, finish.

Data gaps. At the end of the run (done=true), fill wishes with what you wanted to know and the corpus did not hold: topic, why it mattered and for
which market, and what source or kind of data would supply it (a feed, a filing, a dataset, a live statistic). This is feedback to the people who
build the corpus about which data sources to add; it is separate from request_research and it is not a reason to hold off acting. Leave it empty
if nothing was missing; do not invent wishes.

Each turn: put a one-line plan in notes, list the calls, and set done=true (with calls empty or only final orders) when the run is over. When
done, summary is two or three plain sentences: what you looked at, what you did, what you are watching.
"""


MUST_TRADE = """
YOU MUST TRADE. This book exists for fast feedback, so every run has to FILL at least {n} order{s} (a buy or a sell that goes through) within the normal size
caps; a run that ends with fewer is recorded as a failure. Choose the best edge available. If nothing shows a real edge, take the smallest-size position on
your best guess (the minimum ticket) in the market where your probability differs most from the price, and say plainly in your reason that it had no real edge.
Do not skip the research: the point is that the bet is still your honest view.
"""


def _span(hours: float) -> str:
    return {48: "two days"}.get(int(hours), f"{hours / 24:g} days")


def role(strategy: Strategy | None = None) -> str:
    """The agent's standing instructions. The day book (the default) gets exactly its original text; another strategy gets its own horizon, caps, its reasoning
    method (the lab mind's instructions, ``methods.py``) and, if it must trade, the obligation to."""
    s = strategy or strategies.get("day")
    text = ROLE.format(horizon=f"{s.horizon_h:g}", window=f"{s.horizon_h:g}", span=_span(s.horizon_h), per_turn=s.calls_per_turn, pos=s.position_frac, exp=s.exposure_frac,
                       ticket=flags.TRADE_MIN_TICKET, orders=s.max_orders)
    return text + methods.section(s.method) + (MUST_TRADE.format(n=s.min_orders, s="" if s.min_orders == 1 else "s") if s.must_trade else "")


class Call(BaseModel):
    tool: Literal["search_markets", "market", "portfolio", "entity", "about", "search", "timeline", "related", "series", "request_research", "performance", "size", "watchlist", "buy", "sell"]
    query: str = Field(default="", description="search_markets / corpus tools: the words or entity name; request_research: the one specific thing to research.")
    market: str = Field(default="", description="market / buy / sell: the market id.")
    side: Literal["yes", "no", ""] = Field(default="", description="buy: which side to buy.")
    usd: float = Field(default=0.0, description="buy: paper dollars to spend; sell: dollars of current value to sell.")
    all: bool = Field(default=False, description="sell: close the whole position.")
    basis: str = Field(default="", description="buy: your reasoning method's working for this market (see the method section of your instructions); empty if your method asks for none.")
    reason: str = Field(default="", description="buy / sell: the edge or why you are leaving, plain words; request_research: what you would do with it.")
    p_yes: float = Field(default=0.0, description="buy / sell / size: YOUR probability that the market resolves YES, a FRACTION strictly between 0 and 1 (0.07 means 7%; never write 7). 0 means not given.")
    action: Literal["list", "add", "remove", ""] = Field(default="", description="watchlist: what to do.")
    cited: list[str] = Field(default_factory=list, description="buy / sell: corpus ids from results that you relied on.")
    since: str = Field(default="", description="Corpus tools: ISO date to start from, or empty.")
    kinds: list[str] = Field(default_factory=list, description="Corpus tools: optional narrowing (document kinds, or claim / event / document).")
    ends_within_h: float = Field(default=0.0, description="search_markets: hours; 0 means the whole horizon.")
    min_liquidity: float = Field(default=0.0, description="search_markets: minimum liquidity in dollars; 0 means the house floor.")
    limit: int = Field(default=0, description="search_markets: rows; 0 means the default.")


class WishOut(BaseModel):
    topic: str = Field(description="What you wanted to know.")
    why: str = Field(default="", description="Why it mattered, and for which market.")
    market: str = Field(default="", description="The market id it was for, if one.")
    source: str = Field(default="", description="The source or kind of data that would supply it.")


class Turn(BaseModel):
    notes: str = Field(default="", description="One line: what this turn is for.")
    calls: list[Call] = Field(default_factory=list, description="Tool calls to run now, in order.")
    done: bool = Field(default=False, description="True when the run is over.")
    summary: str = Field(default="", description="When done: what you looked at, what you did, what you are watching.")
    wishes: list[WishOut] = Field(default_factory=list, description="When done: what the corpus lacked that you wanted (data-source feedback).")
