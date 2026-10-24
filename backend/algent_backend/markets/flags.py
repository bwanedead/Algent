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
