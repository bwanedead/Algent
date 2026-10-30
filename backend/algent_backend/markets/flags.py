"""
Markets — in-repo operator knobs (no ``.env``). Each number says why it is what it is; retune after a month of resolved markets.
"""

from __future__ import annotations

# ── what is mirrored ─────────────────────────────────────────────────────────────────────────────
#: Polymarket tag slugs swept for candidate events (Gamma ``/events?tag_slug=``). Chosen to cover our theaters: conflict, elections,
#: macro and trade. A market is KEPT only if it then maps to a theater or a country we cover (mapping.py), so a wide net is cheap.
TAGS: tuple[str, ...] = ("geopolitics", "world", "politics", "middle-east", "russia", "ukraine", "china", "elections", "economy", "fed",
                         "iran", "israel", "taiwan", "oil", "tariffs", "nato", "north-korea", "india", "africa", "europe")
#: Events carrying any of these tags are skipped (sports, crypto and culture are not our beat and are priced by other forces).
BLOCK_TAGS: tuple[str, ...] = ("sports", "esports", "crypto", "culture", "pop-culture", "music", "games", "nba", "nfl", "soccer", "mlb", "nhl",
                               "movies", "tv", "celebrities", "memes", "twitter", "tweets", "mention-markets", "bitcoin", "ethereum", "weather")
#: Events fetched per tag (Gamma pages by offset; ordered by 24h volume so the busiest come first).
EVENTS_PER_TAG = 100
#: A market thinner than this (USD) is a poor price: skipped.
MIN_LIQUIDITY_USD = 1500.0
MIN_VOLUME_USD = 5000.0
#: Markets ending sooner than this many hours are skipped (nothing left to forecast); later than this many days, too far to settle soon.
MIN_HOURS_LEFT = 12
MAX_DAYS_AHEAD = 400
#: At most this many open markets are mirrored (highest volume first): a storage and forecasting-cost bound.
MAX_OPEN = 300
#: Minimum mapping score for a market to count as about us (mapping.py: 2 per shared country + 1 per shared distinctive word).
MIN_MAP_SCORE = 2

# ── snapshots ────────────────────────────────────────────────────────────────────────────────────
#: A price snapshot is written at most this often per market (the timer may fire more often).
SNAPSHOT_MIN_GAP_H = 3.0
#: A forecast is compared with the market's snapshot at or before it, at most this many hours older; otherwise there is no comparison.
SNAPSHOT_MAX_AGE_H = 12.0
#: History backfill: CLOB ``prices-history`` for a newly mirrored market, at this fidelity (minutes) over its life.
HISTORY_FIDELITY_MIN = 1440
#: Only the newest this many history points are kept (older context does not change a forecast comparison and bloats the file).
HISTORY_MAX_POINTS = 90
#: A resolved market is judged yes/no when its final YES price is at or beyond these; anything between is a split (50-50) resolution = void.
RESOLVED_YES_AT = 0.99
RESOLVED_NO_AT = 0.01

# ── our forecasts ────────────────────────────────────────────────────────────────────────────────
#: Master switch for the paid forecast pass.
FORECAST_ENABLED = True
#: At most this many markets are forecast per UTC day, and at most this much USD is spent on them (the tighter limit wins).
MAX_FORECASTS_PER_DAY = 40
MAX_FORECAST_USD_PER_DAY = 1.0
#: Per-call hard cap (cost.scoped). A blind forecast is a few thousand input tokens and a short answer.
FORECAST_CALL_CAP_USD = 0.06
#: A market is forecast again only after this many days (forecasts are immutable; a refresh is a NEW line, never an edit).
REFORECAST_DAYS = 7
#: Markets priced at the extremes are not worth a forecast: nobody disagrees with 1% or 99%. This uses the MARKET price only to pick
#: where to spend; the forecast itself never sees the price.
SKIP_BELOW = 0.03
SKIP_ABOVE = 0.97
#: A market is forecast only if the mirror has priced it this recently (a dead mirror means no price band check and no later comparison).
PRICE_FRESH_H = 36.0
#: Theater sections, statements and calendar lines shown to the forecaster, per market.
EVIDENCE_SECTIONS = 3
EVIDENCE_STATEMENTS = 6
EVIDENCE_CALENDAR = 8
#: Extra pieces the retrieval index adds per market (relevance-ranked, across dates and sources; retrieval/flags.py holds the windows).
RETRIEVAL_K = 6
#: Our probability is kept inside these bounds before it is stored or traded, so a log loss is never infinite and we never claim certainty.
P_MIN, P_MAX = 0.01, 0.99

# ── paper portfolio ──────────────────────────────────────────────────────────────────────────────
#: Fixed paper bankroll in paper dollars. Never changes: P&L is measured against it, and sizing is a fraction of it.
BANKROLL = 10000.0
#: Take a position when |ours - market| is at least this (probability points). Below it the disagreement is inside what a model
#: reading headlines can claim to know, and fees/spread on a real venue would eat it.
EDGE_MIN = 0.10
#: Fraction of full Kelly staked (full Kelly is far too aggressive for a model not yet shown to be calibrated).
KELLY_FRACTION = 0.25
#: No single position stakes more than this share of the bankroll; total open stake is capped at MAX_EXPOSURE_FRAC of it.
MAX_POSITION_FRAC = 0.05
MAX_EXPOSURE_FRAC = 0.5
#: Paper fills pay this much more than the quoted price (probability points) to stand in for spread and slippage.
SLIPPAGE = 0.01

# ── the trader: the daily agent book (trader.py), beside the rule book above ─────────────────────
#: Master switch for the paid daily trade pass.
TRADE_ENABLED = True
#: When the unattended ``markets-daily`` job fires (UTC HH:MM): after daily part 1 (05:30, about 70 min) so the desk's newest sections are
#: in the evidence the forecaster and trader read, and before the working day.
DAILY_UTC = "07:30"
#: The trade pass spends at most this much per UTC day, and no single call more than the call cap (cost.scoped). A batch of markets with
#: their evidence is ~10-15k input tokens.
TRADE_MAX_USD_PER_DAY = 0.75
TRADE_CALL_CAP_USD = 0.20
#: Markets per call, and the most markets looked at per day (positions held first, then the widest gaps between our view and the price).
TRADE_BATCH = 8
TRADE_MAX_MARKETS_PER_DAY = 40
#: A market is offered for a NEW position only with a blind forecast of ours at most this many days old (held markets are always shown).
TRADE_FORECAST_MAX_AGE_DAYS = 14
#: Model effort for the trade call (house_spec reasoning_effort).
TRADE_EFFORT = "low"
#: Smallest ticket the book will fill (paper dollars): below it a buy is a clipped hold, so the ledger is not littered with dust.
TRADE_MIN_TICKET = 10.0
#: Evidence shown per market in the trade prompt, in characters (the forecast saw more; the trader needs what changed).
TRADE_EVIDENCE_CHARS = 2400
#: Price path shown per market: one point per day for this many days.
TRADE_PATH_DAYS = 14

# ── corpus-only research (research.py) ───────────────────────────────────────────────────────────
#: Master switch. On, a forecast or a trade decision reads ONLY what the corpus query API returns for queries a cheap planning call proposes (no
#: open-web search anywhere in the decision path). Off, the older blind evidence (evidence.py) is used. The harness has no tool calling, so this
#: is planned retrieval: plan call -> we run the queries against the corpus -> the decision call reads the results.
RESEARCH_ENABLED = True
#: With research on, the decision sees ONLY corpus results (so the track record measures the corpus). False adds evidence.py's blocks beside them.
#: If the corpus index is missing the pass falls back to evidence.py and the trace says so.
CORPUS_ONLY = True
#: Planning rounds per market (forecast) or per batch (trade). A second round sees the first round's result lines and may ask for more.
RESEARCH_MAX_ROUNDS = 2
#: Queries per round (per market), results kept per query, and characters of results shown to the decision call per market.
RESEARCH_QUERIES_PER_ROUND = 4
RESEARCH_ROWS_PER_QUERY = 6
RESEARCH_CHARS_PER_MARKET = 3200
#: Per planning-call hard cap (cost.scoped). A plan is a small structured answer over a short task.
RESEARCH_PLAN_CAP_USD = 0.02
RESEARCH_PLAN_EFFORT = "low"
#: Rows of a corpus answer older than this many days are not offered (a 4-year-old daily does not bear on a question settled this month).
RESEARCH_LOOKBACK_DAYS = 120
#: Research traces (research_trace.jsonl, one line per decision) older than this are pruned by the refresh job; scoring never reads them (the
#: forecast and decision lines carry their own cited ids).
TRACE_KEEP_DAYS = 60
#: "Rich" evidence for the accuracy split: a decision that cited at least this many corpus items; fewer is "thin". Shown only at MIN_RESOLVED_FOR_VERDICT.
RICH_MIN_CITED = 3
#: Items shown in a position's evidence trail on the page.
TRAIL_MAX = 12

# ── gaps: what the bots looked for and the corpus did not hold (gaps.py) ─────────────────────────
#: A gap is a request, never a lookup: it lands in gaps.jsonl and the daily fill job researches it into the corpus through the ordinary research
#: pipeline. The bot sees the result the next time, as corpus content. Operator-authorised ceiling: $0.50 a day.
GAP_FILL_ENABLED = True
#: When the unattended ``markets-gaps`` job fires (UTC HH:MM): after the markets-daily pass (07:30) has recorded the day's asks.
GAPS_UTC = "08:45"
GAP_FILL_USD_PER_DAY = 0.50
#: Each fill is one profile research run. Its estimated cost is booked at this figure per run until the ledger measures it (the budget gate still
#: halts real overspend), so at most GAP_FILL_USD_PER_DAY // GAP_FILL_EST_USD runs a day.
GAP_FILL_EST_USD = 0.25
#: Hard USD cap handed to each research run (the profile loop honours a vector's ``cost_cap_usd``; its own ceiling is $1.00).
GAP_FILL_RUN_CAP_USD = 0.25
GAP_FILL_MAX_PER_DAY = 2
#: A topic asked for again within this many days of a fill is not researched again (the profile store keeps history; the corpus already has it).
GAP_REFILL_DAYS = 14
#: A gap needs at least this many distinct asks (market x decision) to be worth a run, unless it is the only candidate; ties go to the newest.
GAP_MIN_ASKS = 1

# ── the fast book: markets that settle soon, decided every few hours (trader.py with the FAST book) ──
FAST_ENABLED = True
#: Only markets ending within this many days (and no sooner than FAST_MIN_HOURS_LEFT hours) are in the fast book.
FAST_HORIZON_DAYS = 7
FAST_MIN_HOURS_LEFT = 6
#: Cadence of the registry job (hours; the job and this stay in step) and the shortest gap before the same market is decided again.
FAST_EVERY_H = 4
FAST_RECHECK_H = 3.5
#: Spend: per run and per UTC day (forecasts that feed the fast book + its trade call), and markets looked at per run.
FAST_MAX_USD_PER_RUN = 0.12
FAST_MAX_USD_PER_DAY = 0.60
FAST_MAX_MARKETS_PER_RUN = 12
#: A fast market needs a blind forecast no older than this many hours to be offered for a NEW position; a missing or older one is re-forecast
#: (at most FAST_FORECASTS_PER_RUN a run, blind as ever) before the trade call.
FAST_FORECAST_MAX_AGE_H = 36.0
FAST_FORECASTS_PER_RUN = 4

# ── the day book: a 0-2 day agent that browses Polymarket and chooses its own bets (day.py, day_tools.py, browse.py) ──
#: Paper only, a third book beside daily and fast. It is handed no market list: it searches Polymarket live (all categories the blocklist allows)
#: and our mirror, reads our corpus, and buys and sells freely under the same guards. Its own $10k, its own caps, its own spend cap.
DAY_ENABLED = True
#: The unattended ``markets-day`` job fires at these hours, every day, at minute DAY_RUN_MINUTE (UTC). Chosen to miss the 05:00-07:00 crunch (menu,
#: dailies, ai-bench, backups) and to sit 20 minutes after the fast book's :20 pass.
DAY_RUN_HOURS: tuple[int, ...] = (8, 14, 20)
DAY_RUN_MINUTE = 40
#: Markets browsed and tradable: ending within this many hours (and no sooner than DAY_MIN_HOURS_LEFT). Searches default to the full window.
DAY_HORIZON_H = 48
DAY_MIN_HOURS_LEFT = 1.0
#: Liquidity and volume floors use the mirror's (MIN_LIQUIDITY_USD, MIN_VOLUME_USD) and the category blocklist is BLOCK_TAGS: one definition of
#: "a market worth trading". Rows the browser returns per search.
DAY_SEARCH_LIMIT = 10
DAY_SEARCH_LIMIT_MAX = 25
#: Own book: the same fixed paper $10k and caps as the others unless retuned here (guards.apply takes these).
DAY_BANKROLL = BANKROLL
DAY_MAX_POSITION_FRAC = 0.05
DAY_MAX_EXPOSURE_FRAC = 0.5
#: The tool loop's bounds. It is a loop of structured turns on the house model (no native tool calling in this harness): each turn the agent names
#: tool calls, we execute them, it reads the results and names more, until it says it is done or a bound is hit. Spend: per run, per UTC day
#: (operator ceiling $0.50, inside the global spend halt) and per model call.
DAY_MAX_TURNS = 7
DAY_MAX_TOOL_CALLS = 24
DAY_MAX_CALLS_PER_TURN = 6
DAY_MAX_ORDERS_PER_RUN = 6
DAY_MAX_USD_PER_RUN = 0.15
DAY_MAX_USD_PER_DAY = 0.45
DAY_CALL_CAP_USD = 0.05
DAY_EFFORT = "low"
#: What one tool result may show the agent (characters), and how much of the transcript is re-sent each turn (older results are collapsed to a line).
DAY_RESULT_CHARS = 1800
DAY_TRANSCRIPT_CHARS = 26000
#: The recent price path shown by market(): hourly points over this many hours, thinned to at most this many.
DAY_PATH_HOURS = 24
DAY_PATH_POINTS = 12
#: The page lists this many recent runs (compact "what it browsed and why"); run lines older than TRACE_KEEP_DAYS are pruned with the other traces.
DAY_RUNS_SHOWN = 12
#: Win rate and P&L by hold horizon (hours between entry and the market's end) are shown only once a bucket holds MIN_RESOLVED_FOR_VERDICT closed positions.
DAY_HORIZON_BUCKETS: tuple[tuple[str, float, float], ...] = (("under 6 hours", 0.0, 6.0), ("6 to 24 hours", 6.0, 24.0), ("24 to 48 hours", 24.0, 1e9))

# ── the strategy roster (strategies.py): every bot is its own forecaster and decision-maker, run by the generic loop in day.py ──
#: No desk forecast feeds any bot. The mechanical rule book needed one (it traded the desk's probability on a fixed edge rule), so it is RETIRED: no new
#: positions (its history stays on the page, marked and settled); a rule-sized strategy would be a new roster entry, not this switch.
RULE_BOOK_ENABLED = False
STRAT_ENABLED = True
#: Defaults for the independent strategies (the day book keeps its DAY_* numbers, daily/fast their own below). Target: <= $0.15 a run, about $3 a day for the whole roster:
#: day 0.45 + daily 0.25 + fast 0.40 + five strategies at 0.40 = $3.10 ceiling (typical runs cost less).
STRAT_HORIZON_H = 168                      # 0-7 days, so results come back fast
STRAT_MAX_USD_PER_RUN = 0.15
STRAT_MAX_USD_PER_DAY = 0.40
STRAT_MAX_TURNS = 7
STRAT_MAX_TOOL_CALLS = 24
STRAT_MAX_CALLS_PER_TURN = 6
STRAT_MAX_ORDERS_PER_RUN = 6
STRAT_CALL_CAP_USD = 0.05
STRAT_EFFORT = "low"
#: The old daily trader and fast book as roster strategies: same books and ledgers (continuous history), now forming their own probabilities.
DAILY_STRAT_HORIZON_H = 24 * 30
DAILY_STRAT_MAX_USD_PER_DAY = 0.25
FAST_STRAT_MAX_USD_PER_RUN = 0.07
FAST_STRAT_MAX_USD_PER_DAY = 0.40
#: The hourly desk (Baseline research): every hour, only markets ending within HOURLY_HORIZON_H hours (and not within HOURLY_MIN_HOURS_LEFT), with a per-DAY
#: fill minimum: owed only on the day's last scheduled run, never faked (an unmet day is recorded unmet). Per-run cost is small; 24 runs a day share the day cap.
HOURLY_ENABLED = True
HOURLY_HORIZON_H = 12
HOURLY_MIN_HOURS_LEFT = 1.0
HOURLY_RUN_MINUTE = 25
HOURLY_MIN_FILLS_DAY = 1
HOURLY_STRAT_MAX_USD_PER_RUN = 0.05
HOURLY_STRAT_MAX_USD_PER_DAY = 0.35
#: A must-trade run that has not filled its minimum is sent back to trade at most this many times before it is recorded as unmet.
MUST_TRADE_PUSHES = 2

# ── forecast feedback and activity floors (day.py, bot_forecasts.py): feedback does not depend on trading ──────────────────────────
#: Every run records its OWN probability for at least this many markets it examined, traded or not (the Turn's ``forecasts`` list: output tokens only, no
#: order). A run that ends short is sent back to top up, at most FORECAST_PUSHES times, then recorded short. Scored on resolution (Brier, log loss, vs the
#: market price at forecast time) in an append-only per-strategy log no other bot reads. Lots of scored predictions a day, independent of trading.
FORECASTS_PER_RUN = 8
FORECAST_PUSHES = 2
#: Most forecasts one turn may carry (a bound on output size); a market is forecast once per run (a restated one replaces the earlier line in that run only).
FORECASTS_PER_TURN = 12
#: A bot's Brier is shown only once it has this many RESOLVED forecasts; before it the page says "n=3, too early".
FORECAST_MIN_RESOLVED = 10
#: Minimum activity: the share of the bankroll that should be at risk after each run. Below it the agent is told and must add positions on its best-edge
#: markets; with no edge it takes small positions sized by its own probability vs the price (fractional Kelly, min ticket, same guards). The floor is
#: clamped to FLOOR_CAP_SHARE of the strategy's exposure cap (guards stay: 50% total), so a 60% target means 45% in practice.
#: OFF since 10-30: the floor made bots park the bankroll in the same near-certain bets (no edge, no signal). Resting orders, the per-run must-trade
#: minimum and the hourly desk's daily fill minimum keep bots active instead. Set above 0 to turn it back on.
MIN_EXPOSURE_PCT = 0.0
MUST_TRADE_MIN_EXPOSURE_PCT = 0.0
FLOOR_CAP_SHARE = 0.9
FLOOR_PUSHES = 2
#: A buy made while the book is under its floor is tagged ``floor`` when the agent says it is only filling the floor OR its own edge on that side is
#: below EDGE_MIN: those positions are measured apart from chosen ones. Floor buys are sized at the Kelly stake on the agent's own p, never below the
#: minimum ticket and never above the guards.

# ── scoring ──────────────────────────────────────────────────────────────────────────────────────
#: Calibration buckets are this wide (probability): ten of them.
CALIBRATION_BUCKET = 0.1
#: Scores are not called meaningful until this many markets have resolved with a forecast of ours; before it the page says so plainly.
MIN_RESOLVED_FOR_VERDICT = 30
#: How many resolved markets the published document lists.
PUBLISH_RESOLVED = 200
#: The daily's "where we disagree" line: the gap needed (probability points) and the most lines shown.
DISAGREE_MIN = 0.15
DISAGREE_LINES = 4
#: A forecast older than this many days is not offered as "our current view" in the daily line.
DISAGREE_MAX_AGE_DAYS = 10

# ── resting limit orders (resting.py): paper only, filled by a free price pass with no model call ─────────────────────────────────
#: A bot may leave a limit order that waits between its runs and fills when the price reaches it. Off = the tools refuse and the pass fills nothing (open orders then just expire).
RESTING_ENABLED = True
#: Open resting orders one book may hold at once.
RESTING_MAX_OPEN = 6
#: The longest an order may rest, in hours (it is also capped at the market's end).
RESTING_MAX_HOURS = 48.0
#: The pass fills only against a price snapshot at most this old (the pass refreshes the quotes of the markets it watches first); an older one is skipped, not guessed.
RESTING_MAX_SNAPSHOT_AGE_H = 2.0
#: Recent resting fills listed per bot in the published document.
RESTING_FILLS_SHOWN = 8
