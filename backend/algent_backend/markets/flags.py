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
