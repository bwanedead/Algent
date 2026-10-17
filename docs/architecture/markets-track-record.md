# Markets track record (paper-trading against Polymarket)

A reality feedback loop. A system that only reads itself drifts into delusion; this one is scored by the world. For Polymarket markets on topics the desk
covers, Ohmega forecasts **blind to the price**, stores the forecast immutably, and when the market resolves both we and the market are scored against what
happened. **Paper only**: there is no wallet, no key and no order function anywhere; nothing here is financial advice. Code: `backend/algent_backend/markets/`;
CLI `newsroom markets ...`; site `/intel/track-record`, `/api/v1/track-record`; the daily's "Where we disagree with the market".

## Pipeline
1. **Mirror** (`mirror.py`, free; timer `ohmega-markets` every 4 h). Gamma `GET /events?tag_slug=<tag>&active=true&closed=false&order=volume24hr` for each tag in
   `flags.TAGS`; events with a tag in `flags.BLOCK_TAGS` (sports, crypto, culture...) are dropped. Binary Yes/No markets only, liquid (`MIN_LIQUIDITY_USD`,
   `MIN_VOLUME_USD`), ending inside the window, mapped to us (below), highest volume first, at most `MAX_OPEN`. CLOB `GET /prices-history?market=<yes token>`
   backfills a new market's daily history. Gamma `GET /markets/{id}` is how a tracked market that left the sweep is seen to have **resolved**: closed with a
   final price at or beyond `RESOLVED_YES_AT`/`RESOLVED_NO_AT` is yes/no; a settled 50-50 is `void`. All append-only (`markets_store/`, `ALGENT_MARKETS_STORE`).
2. **Forecast** (`forecast.py`, **paid, manual**: `newsroom markets forecast`). One structured call per market: the question, the market's own resolution rules and
   `evidence.py`'s blind evidence. Capped per day (`MAX_FORECASTS_PER_DAY`, `MAX_FORECAST_USD_PER_DAY`) and per call (`FORECAST_CALL_CAP_USD`), under the budget gate
   (a spend halt refuses it). Cost is roughly a few thousandths of a dollar to a cent a market at low effort, so a full 40-market day is well under the $1 cap.
3. **Paper portfolio** (`paper.py`, free; runs after every mirror pass). **Score** (`score.py`). **Publish** (`publish.py`: `data/track-record.json` in
   `published_intel_documents`, no new migration). **Daily line** (`desk.py`).

## Which markets are "ours" (`mapping.py`)
Soft by design: a mapping only picks evidence and decides what is worth mirroring; every forecast of ours on a resolved market is scored regardless. Countries are
found in the question/event title by whole-word match on the one country table (`actors.registry`; demonym suffixes allowed, "US"/"EU" must be capitalised).
Theaters come from the newest daily's sections (name, headline, the actors and places its developments name): 2 points per shared country, 1 per shared distinctive
word, `MIN_MAP_SCORE`. Known imprecision: a name collision ("Georgia" the US state vs the country) maps to the country; calendar items are matched by country at
evidence time instead.

## The forecast prompt doctrine (`forecast.ROLE`)
Blind by construction: the model is told it is deliberately not given what any market thinks and must not guess it, because an anchored forecast measures only
how well we copy. `evidence.build` takes no price and the module cannot import the snapshots (a test pins both). The role teaches: start from the base rate for
this kind of event over this much time (most dated "by D" questions resolve NO); read the resolution rules literally and note the time left; treat the desk's
sections, statements and calendar items as signals not ground truth; "no information beyond the base rate" is a legitimate answer; be calibrated not cautious (never
0% or 100%); cite only evidence ids shown (others are dropped). The price is first read after the forecast is committed. The daily's market line is attached after
the writers finish, so the loop cannot feed back: the desk informs the forecast, the market never informs the desk.

## Paper rule (all numbers in `flags.py`)
Open when `|ours - market| >= EDGE_MIN` (10 pts); YES if we are above, NO if below; fill at the side's price + `SLIPPAGE`; stake = `KELLY_FRACTION` (0.25) of full Kelly
`(q - c)/(1 - c)` of a fixed `BANKROLL` ($10,000, not compounded), capped at `MAX_POSITION_FRAC` (5%) per position and `MAX_EXPOSURE_FRAC` (50%) open. One position per
market, never added to, flipped or closed early. Marked daily at the side's current price; settled 1/0 per share, 0.5 on void.

## Scoring math (`score.py`)
For each resolved yes/no market with a forecast of ours the pair is (our p, the market's YES price at the forecast's timestamp: the last live snapshot at or
before it, at most `SNAPSHOT_MAX_AGE_H` old, the outcome). The headline uses each market's **first** forecast. Brier = mean (p - o)^2; Brier skill = 1 - Brier_ours / Brier_market
on the same pairs; log loss = mean -(o ln p + (1-o) ln(1-p)) with p clipped to [0.001, 0.999]; calibration = pairs bucketed by stated probability
(`CALIBRATION_BUCKET`); over time = running mean of (Brier ours - Brier market) in resolution order. `verdict` says "too early" until `MIN_RESOLVED_FOR_VERDICT` (30) compared
pairs. The page lists our worst misses first and shades markets where the market was closer. Settled Pulse watches (triggered vs expired: a condition, so hit-rated
not Brier-scored) and the older desk judgment ledger (`intel/forecasts.py`, Brier) are shown beside.

## Operating it
`newsroom markets refresh` (mirror + paper + publish), `forecast [--limit N] [--dry-run]`, `paper`, `score [--full]`, `list`, `status`, `publish`. Doctor check `markets`
(a good pass within 10 h). **The forecast is deliberately not on a paid timer**: the three unattended paid jobs are an operator authorisation (`ops/flags.py`,
`infra/server/jobs.sh`); adding a fourth is the operator's call. To schedule it, add a `forecast` job to `ops/schedule.jobs()` (argv `("markets", "forecast")`, after daily-1) so it
inherits the kill switch, runner claim, spend halt and retry.
