# Markets track record (paper-trading against Polymarket)

A reality feedback loop. A system that only reads itself drifts into delusion; this one is scored by the world. For Polymarket markets on topics the desk
covers, Ohmega forecasts **blind to the price**, stores the forecast immutably, and when the market resolves both we and the market are scored against what
happened. On top of that a **trader agent** manages a paper portfolio every day, so the page shows whether judgement layered on the forecast makes money
(below: *The trader*). **Paper only**: there is no wallet, no key and no order function anywhere; nothing here is financial advice. Code: `backend/algent_backend/markets/`;
CLI `newsroom markets ...`; site `/intel/track-record`, `/api/v1/track-record`; the daily's "Where we disagree with the market".

## The strategy roster (10-28): every bot is its own forecaster
**Supersedes the "desk forecast feeds the trader / rule book / fast book" parts below.** No desk forecast feeds any bot. Each live paper bot is one entry in `markets/strategies.py`
(id, name, reasoning method, style, horizon, run times, $ caps, `must_trade` + minimum orders) and is run by ONE generic loop (`day.run(strategy_id=...)`, the day-book loop
generalised: browse markets -> corpus research -> form its own probability -> buy / sell / hold under `guards.py`). A strategy never reads another's forecasts, orders, watchlist or
traces, and the code path cannot reach a forecast store (a test pins it). Each has its own $10,000 book (`Decision.book` = the id), run traces (`DayRun.strategy`), wishes, watchlist
and equity series.

**Reasoning methods are the lab's minds** (`markets/methods.py` reads `experiment/minds.py` lazily; the lab ids stay the source of truth): `p0b` baseline research, `p0b+prior` base
rate first, `b` delineation, `b+prior` delineation + base rate (P3). The lab's addendum is appended to the live role and its schema fields are listed as the working to write in the
order's `basis` (stored on the ledger line); `probability_pct` / `rationale` / `cited` map to `p_yes` / `reason` / `cited`.

| id | method | style | horizon | runs (UTC) | $/run, $/day |
|---|---|---|---|---|---|
| `day` | baseline | opportunistic, 0-2 days | 48 h | 8, 14, 20 :40 | 0.15, 0.45 |
| `daily` (book `daily`, series `trader`) | baseline | patient, once a day | 30 d | 07:30 | 0.15, 0.25 |
| `fast` (book `fast`) | baseline | short horizon, every 4 h | 7 d | 0,4,..20 :20 | 0.07, 0.40 |
| `base-rate` | base rate first | earns its edge | 7 d | 9, 13, 17, 21 :05 | 0.15, 0.40 |
| `delineation` | delineation | maps outcomes first | 7 d | 10, 14, 18, 22 :05 | 0.15, 0.40 |
| `delineation-base-rate` | delineation + base rate | both | 7 d | 11, 15, 19, 23 :05 | 0.15, 0.40 |
| `baseline-must-trade` | baseline | must fill 2 orders a run | 7 d | 9, 13, 17, 21 :35 | 0.15, 0.40 |
| `delineation-must-trade` | delineation | must fill 1 order a run | 7 d | 10, 14, 18, 22 :55 | 0.15, 0.40 |

Ceiling about $3.10 a day for the roster (typical runs cost less; measure from `day_runs.jsonl`). `daily` and `fast` keep their old ledgers and equity series, so history is
continuous; they just stop reading desk forecasts. **Must-trade** (feedback speed only, labelled on the page): a run that says it is done before filling its minimum (a buy or sell
that went through; a refused or clipped-to-nothing order does not count) is sent back to trade up to `MUST_TRADE_PUSHES` times and the last turns are told how many orders it owes, at the
smallest size if nothing has edge; a run still short is recorded `DayRun.must_trade = "unmet: n of m"`, never faked. Normal size caps apply.

**Retired / demoted.** The rule book needed a desk probability, so it is **retired** (`flags.RULE_BOOK_ENABLED = False`: it opens nothing, still marks and settles what it holds; shown
under "Retired"). The desk forecaster (`forecast.py`, `markets forecast`) is no longer scheduled in `markets daily` / `markets fast` and the old `markets trade` verb is gone; the code
stays as the lab's frozen P0 / P0b control and for scoring past forecasts ("How good are the forecasts?"). `trader.py` / `trader_prompt.py` are the frozen replayable trader control only.

**Schedule.** One capped registry job per strategy (`markets-<id>`, `newsroom markets strategy <id>`; `markets-day`, `markets-daily`, `markets-fast` keep their verbs), editorial priority,
staggered at least 10 minutes apart and off 05:00-07:00 (a test pins it). `newsroom markets strategy --list` prints the roster.

**Page** (`ohmega.track-record/2`, additive `strategies[]`, one section per strategy shaped like `day` plus `id, name, method, method_name, style, must_trade, min_orders, next_run`): one value
chart with a line per bot labelled at its end (must-trade dashed), one table row per bot (name, method, style, value, P&L, open, trades, last run, next run) grouped by method, expanding
to positions, trades with reasons, its latest run (with the must-trade check) and wishes. Documents from before the roster fall back to the three old books.

## Sizing and trust (`sizing.py`; 10-31)
The hourly bot bought 95-99c "sure things" at $500 (the 5% cap): ten wins made $27, two losses cost $970. The forecaster's job is a probability; sizing is mechanical and lives in ONE
module that every buy path uses (`guards.apply` for agentic buys and resting placement/fills, `guards.floor_stake`, and `paper.kelly_stake` for the rule book's full-Kelly maths).
- **Shrink.** `q = w*p + (1-w)*price` for the side, where `w` is the strategy's TRUST and `price` the side's quote (slippage is added to the cost, not to the anchor).
- **Ceiling.** `KELLY_FRACTION x (q - c)/(1 - c) x bankroll` on the all-in cost `c`. `q <= c`: no trade, held, clip "no edge after trust shrink". The agent's stake is honoured only up
  to the ceiling ("trimmed to trust-weighted Kelly $X"); the usual position/exposure/cash caps then apply. A buy with no `p_yes` is refused (it cannot be sized).
- **Extreme prices.** When `c > EXTREME_PRICE` (0.90) the stake is also capped at `MAX_LOSS_FRAC_EXTREME` (1%) of the bankroll: the whole stake is the loss if it fails.
- **Trust** `w = clamp(TRUST_PRIOR + TRUST_GAIN x t, TRUST_MIN, TRUST_MAX)` = `0.3 + 0.1 t` in [0.1, 0.8], `t` = contested skill / its standard error (below). Monotone in skill, grows with
  evidence at equal skill, negative skill lowers it; with fewer than `FORECAST_MIN_RESOLVED` contested resolved forecasts there is no `t` and trust stays at the prior. `size()` shows the agent its trust and ceiling.
- **Unchanged.** Sells. The retired rule book keeps full trust and no extreme cap (it opens nothing now), so its history is not rewritten. A floor position (`MIN_EXPOSURE_PCT`, off) is sized
  by `floor_stake` on the same ceiling and skips the edge test (its point is a ticket with no edge).
- Hourly repro (tested): p=0.995 at 97c, trust 0.3: q=0.9775 < cost 0.98, held. At maximal trust it is capped at $100.

## Skill vs market (`bot_forecasts.skill_stats`)
Brier against the outcome looks great (~0.03) when a bot forecasts near-decided markets; the number that says anything is Brier against the market's price at the same moment. Per strategy,
`forecasts.skill` = `{min_resolved, all, contested}`, each block `{n, shown, mean, se}`: `mean` is the average of (market Brier - bot Brier) on `BotForecast.market`, positive = we beat the market;
`se` is the standard error of that mean. `contested` keeps forecasts whose market price was in `CONTESTED_LO..CONTESTED_HI` (0.05..0.95) at forecast time. **One forecast per (strategy, market): the LAST
made before the market resolved**, so a bot restating a view 20 times counts once (the older per-forecast Brier/log-loss in the same block still count every restatement). `mean`/`se` are
null (`shown` false) until `n >= FORECAST_MIN_RESOLVED`; the page then says "n=8, too early". Additive field of `ohmega.track-record/2` (`contracts/shapes.py`). Site: pill "vs market +0.012 (n=24)" under
the value, and in the detail "Against the market price at the same moment: +0.012 Brier on 24 resolved (contested only: -0.004 on 9)."

## Pipeline
1. **Mirror** (`mirror.py`, free; timer `ohmega-markets` every 4 h). Gamma `GET /events?tag_slug=<tag>&active=true&closed=false&order=volume24hr` for each tag in
   `flags.TAGS`; events with a tag in `flags.BLOCK_TAGS` (sports, crypto, culture...) are dropped. Binary Yes/No markets only, liquid (`MIN_LIQUIDITY_USD`,
   `MIN_VOLUME_USD`), ending inside the window, mapped to us (below), highest volume first, at most `MAX_OPEN`. CLOB `GET /prices-history?market=<yes token>`
   backfills a new market's daily history. Gamma `GET /markets/{id}` is how a tracked market that left the sweep is seen to have **resolved**: closed with a
   final price at or beyond `RESOLVED_YES_AT`/`RESOLVED_NO_AT` is yes/no; a settled 50-50 is `void`. All append-only (`markets_store/`, `ALGENT_MARKETS_STORE`).
2. **Forecast** (`forecast.py`, **paid, manual**: `newsroom markets forecast`). One structured call per market: the question, the market's own resolution rules and
   the evidence (since 10-23 the corpus's results for planned queries, see *Corpus-only research*; before, `evidence.py`'s blind evidence). Capped per day (`MAX_FORECASTS_PER_DAY`, `MAX_FORECAST_USD_PER_DAY`) and per call (`FORECAST_CALL_CAP_USD`), under the budget gate
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

## The trader (`trader.py`, `trader_prompt.py`, `guards.py`, `book.py`, `trader_report.py`)
Layered ON the blind forecast, never replacing it: the forecast stays the honest calibration signal (it never sees a price); the trader is shown our probability
**and** the price and acts. Two books start from the same fixed $10,000 and are valued by the same code (`book.py`: holdings at the side's current price, payout 1/0/0.5):

| book | who decides | closes early | ledger |
|---|---|---|---|
| **trader** (the agent) | the model, once a day | yes (sell, reduce, add) | `decisions.jsonl` |
| **rule book** (`paper.py`, the baseline) | the edge rule (>= 10 pts, quarter Kelly) | never | `trades.jsonl` |

A flat $10,000 line (doing nothing) is the third curve. `equity.jsonl` holds one point per book per day, written once and never replaced (`book.mark`).

**A day** (`trader.run`): settle held markets that resolved (free; also done in `refresh`) -> candidates: every held market first, then open markets with a forecast of ours
at most `TRADE_FORECAST_MAX_AGE_DAYS` old and a fresh price, widest gap first, at most `TRADE_MAX_MARKETS_PER_DAY` -> batches of `TRADE_BATCH` (8): per market the
question, resolution rules, our probability and reasoning, price now and a daily path, days left, the position (entry, cost, worth) and evidence (`evidence.build` plus
retrieval, clipped to `TRADE_EVIDENCE_CHARS`) -> one structured call per batch (flat schema `TraderOut`: market label, `buy_yes|buy_no|sell|hold`, `stake_usd`, a
one-or-two-sentence plain-English rationale) -> every call goes through `guards.apply` -> one `Decision` line per market, **holds and clipped requests included**.
The role (`trader_prompt.ROLE`) teaches: a gap is a reason to look, not to trade; hold is the default; slippage eats small gaps; time-to-resolution and capital; size by
evidence not by gap; sell when the reason is gone, not when the position is down.

**Guards are code, not prompt** (`guards.py`; numbers in `flags.py`): cash can never go negative; `MAX_POSITION_FRAC` (5% of the fixed bankroll, adds counted) per
market and `MAX_EXPOSURE_FRAC` (50%) in total; no shorting (the only bet against an outcome is buying the other side, and holding both sides is refused: sell first); fills
pay `SLIPPAGE` against the book (buys above the quote, sells below it); only open, freshly priced markets trade; a ticket under `TRADE_MIN_TICKET` is not filled; a sell
cannot exceed the position. A cut is never silent: `Decision.clips` records how a request was trimmed and the page prints it. An unanswered market is a recorded hold.
Idempotent per day: a market already decided today is not asked again, so a rerun after a failure repays nothing.

**Cost** (`flags.py`): `TRADE_MAX_USD_PER_DAY` $0.75 and `TRADE_CALL_CAP_USD` $0.20 per call, under the budget gate (a spend halt refuses it); the forecast pass keeps its own
$1.00/day and 40-market caps. Expected: ~40 markets in 5 batches at ~10-15k input tokens each is roughly $0.20-0.50 a day for the trader at low effort, and the forecast pass
a few cents to a few tens of cents a day (it works through the ~300 open markets at up to 40 a day for the first week, then only new markets and weekly refreshes,
`REFORECAST_DAYS` 7). Ceiling $1.75/day, typical well under $1. These are estimates, not measurements: the `usd` fields in `decisions.jsonl` and `forecasts.jsonl` after the first
daily are the real numbers.

**The page** (`/intel/track-record`, payload schema `ohmega.track-record/2`, `trader` object): equity curve (trader, rule book, flat), positions held with the agent's last
words, every trade newest first with its outcome once resolved (green won, red lost), then the existing calibration and misses. A schema-1 document still parses (empty trader).

## Corpus-only research (`research.py`, `trace.py`, `trail.py`; 10-23)
The goal: the bots decide from OUR corpus, so the track record measures what the corpus knows and nothing else drives an outcome. **No open-web search is in the decision
path.** The model harness (`forecast.default_ask`) is one structured call with no tool calling, so this is **planned retrieval**, not a tool loop:
1. A cheap planning call (`research.PLAN_ROLE`, `RESEARCH_PLAN_EFFORT`, capped at `RESEARCH_PLAN_CAP_USD`) is shown the question(s) (never a price) and names corpus queries over the
   six tools of `corpus/query` (`entity`, `about(since, kinds)`, `search`, `timeline`, `related`, `series`). A trade batch of 8 markets is ONE plan call.
2. We run them against the index (`Corpus.open()`, read-only). Round two sees round one's result lines and may ask for more. Caps (flags): `RESEARCH_MAX_ROUNDS` (2),
   `RESEARCH_QUERIES_PER_ROUND` (4 per market), `RESEARCH_ROWS_PER_QUERY` (6), `RESEARCH_CHARS_PER_MARKET` (3200; the trader `TRADE_EVIDENCE_CHARS`), `RESEARCH_LOOKBACK_DAYS`.
3. The decision call reads the rendered results (each row has a bracketed, citable id) and answers with `cited`, `evidence` (`sufficient | thin | gap`, its own verdict) and,
   when it needed something the corpus lacked, `gap_topic` + `gap_why`. Only ids that were actually shown are kept as cited.
With `CORPUS_ONLY` (default) the decision sees only those rows; off, `evidence.py`'s blocks are added. If no corpus index exists on the machine the pass falls back to `evidence.py`
and the trace says `base-fallback` (such a decision has no verdict and files no gap). `RESEARCH_ENABLED = False` restores the old path wholesale.
**Blindness is enforced in the tool layer.** The corpus also ingests the Polymarket mirror, our forecasts and decisions (`corpus/sources/markets.py`); `research._blocked` drops any
row of product `markets`, any `market:` entity and any `market.*` series, whichever tool returned it, so a price or our earlier call can never reach a forecaster.
Planning cost is added to the forecast's/decision's `usd`, so the existing per-day caps still bound everything.

**The trace** (`research_trace.jsonl`, one line per forecast or trade: queries with tool/arg/results/ids/ms/errors, ids returned, ids shown, ids cited, the verdict, estimated tokens
(chars/4: the harness reports cost, not tokens), planning and total USD, latency). Observability only, so it is **pruned after `TRACE_KEEP_DAYS` (60)** by the free refresh pass;
forecasts and decisions carry their own cited ids, which is all scoring reads.

## Gaps feed the corpus, never the bot (`gaps.py`)
A thin/gap verdict with a `gap_topic` appends one line to the append-only `gaps.jsonl` (once per market and topic). `gaps.clusters` merges near-duplicate asks (token-set overlap,
60%) and ranks by how many markets asked. The registry job **`markets-gaps`** (paid, 08:45 UTC, `newsroom markets gaps`) takes the most-asked unfilled clusters and runs each as a
`signal_profile` research run (the existing profile pipeline: web research -> profile store -> corpus index on the next build) with `requested_by: "markets"` on the vector, copied
onto the `SignalProfile`, and a per-run USD cap (`GAP_FILL_RUN_CAP_USD`, honoured by `research/loop._run_cap`). **Caps:** `GAP_FILL_USD_PER_DAY = 0.50` (operator-authorised),
runs booked at `GAP_FILL_EST_USD = 0.25` whether or not they succeed, `GAP_FILL_MAX_PER_DAY = 2`, a filled topic is not run again for `GAP_REFILL_DAYS`, a topic that failed twice is
parked. Each run is one line in `gap_fills.jsonl`. The bots see the answer only when the next corpus build ingests the profile.

## The fast book (`books.py`; `trader.run(book_name="fast")`)
The same trader code, guards, ledger format and arithmetic on a short clock, to compare predictive ability by horizon. Only markets ending within `FAST_HORIZON_DAYS` (7) and no sooner
than `FAST_MIN_HOURS_LEFT`; decided every `FAST_EVERY_H` (4) hours (a market is not asked again within `FAST_RECHECK_H`); its own $10k `BANKROLL`, ledger lines tagged `book: "fast"` in
`decisions.jsonl` (lines without the tag are `daily`), equity series `fast` (written by `book.mark` once it has traded). Registry job **`markets-fast`**, `newsroom markets fast`,
at :20 every 4 h (30 min after the free mirror pass), priority 2 so the editorial dailies win the job lock, `max_wait_min` 45 then skipped as busy. Spend: `FAST_MAX_USD_PER_RUN`
(0.12; forecasts take at most half of it) and `FAST_MAX_USD_PER_DAY` (0.60), forecasts + trade call together. A fast market needs a blind forecast no older than
`FAST_FORECAST_MAX_AGE_H`; the run first forecasts up to `FAST_FORECASTS_PER_RUN` that lack one (blind as ever, `Forecast.book = "fast"`). The scheduler's paid class is daily-only
(`ops/products/validate.py`), so the job is registered `capped` and `markets fast` applies the same gate as a paid job (`ops.schedule._may_spend`: kill switch, runner claim, spend halt).

## The day book (`day.py`, `day_tools.py`, `day_prompt.py`, `browse.py`, `day_report.py`; 10-24)
A third paper book, **agentic and choosing its own bets**, 0-2 days out. It is handed no market list: it browses Polymarket live and our mirror, reads the corpus (the six corpus tools, the same blindness filter, no
open-web search), files research requests, and buys and sells freely at the live price plus `SLIPPAGE`. Same code underneath as the others: `guards.apply` (now taking the book's own caps), `book.holdings/cash/point`,
`Decision` lines tagged `book: "day"` in `decisions.jsonl`, `trader.settle(book_name="day")`, the gap ledger (`request_research` files a `book: "day"` gap), `book.mark` (equity series `day`). Its own $10k and caps:
`DAY_BANKROLL`, `DAY_MAX_POSITION_FRAC` 5%, `DAY_MAX_EXPOSURE_FRAC` 50%.

**Loop approach: a bounded loop of structured turns, not native tool calling.** The harness (`forecast.default_ask`: house model, structured output, per-call `cost.scoped` cap, budget gate) has no tool calling, and `bind_tools`
exists only in the gate for ReAct agents. Each turn the agent returns a `Turn` (notes, up to `DAY_MAX_CALLS_PER_TURN` `Call`s, `done`, `summary`, `wishes`); we execute the calls in order and the next turn reads the transcript (older results
collapse to a line past `DAY_TRANSCRIPT_CHARS`). Bounds in `flags.py`: `DAY_MAX_TURNS` 7, `DAY_MAX_TOOL_CALLS` 24, `DAY_MAX_ORDERS_PER_RUN` 6, `DAY_MAX_USD_PER_RUN` 0.15 (stops before a turn if spend plus the dearest turn so far would
exceed it), `DAY_MAX_USD_PER_DAY` 0.45 (<= the operator's 0.50; summed over `day_runs.jsonl`), `DAY_CALL_CAP_USD` 0.05 a call. The last turns are told they are near the end. A failed model call keeps the orders already filled.

**Tools.** `search_markets(query, ends_within_h, min_liquidity, limit)`: Gamma `/events` swept by end-date window (busiest first) plus `/public-search` for a query, plus the mirror; every row passes `browse.tradable_why` (open, not
in `BLOCK_TAGS`, ends between `DAY_MIN_HOURS_LEFT` and `DAY_HORIZON_H` (48 h, the ceiling), `MIN_LIQUIDITY_USD`/`MIN_VOLUME_USD`, priced). `market(id)`: rules, end, YES/NO, spread and **CLOB book depth** (`/book`, dollars within 5 pts of
each side), recent hourly path. `portfolio()`: cash, % of bankroll at risk, per position cost basis, mark, unrealised and realised P&L, hours to resolution (live marks, snapshots appended). `performance()`: equity history, win rate, average
hold, best/worst, by horizon and category (`day_report.stats`). `size(market, p_yes)`: fractional Kelly for each side with the day caps and cash applied. `watchlist(add|remove|list)`: persisted in `day_watchlist.jsonl`, shown at the start of
every run. `entity/about/search/timeline/related/series`, `request_research`, `buy(market, side, usd, reason, cited, p_yes)`, `sell(market|P#, usd|all, reason, cited, p_yes)`. **Exits are free** and the role makes the agent state
hold-versus-sell-now expected value. Orders return filled / trimmed / refused with the reason to the agent; a refused order is a `hold` line whose `clips` begin `refused:`. A bought market not in the mirror is saved with
`Market.origin = "day"` so the free refresh tracks, marks and resolves it, and the desk's forecaster never forecasts it.

**Meta-goal and data-gap feedback.** The role opens with compounding the bankroll reliably, risk-adjusted. Every run ends with `wishes` (topic, why, market, the source or data type that would supply it) persisted to `day_wishes.jsonl`
(one line per topic per run), merged across runs by `gaps` token similarity (`day_report.wishes_top`, ranked by distinct runs) and shown as "What it wished we knew": product feedback on which data sources to add, separate from
`request_research` (a topic to research now, filled by `markets-gaps`).

**Trace.** `day_runs.jsonl`, one `DayRun` per run: every tool call (args, what the agent was shown, ms, the ledger line an order produced), markets considered, corpus queries, orders, closing note, estimated tokens, USD, why it
stopped, equity after. Pruned with the research traces at `TRACE_KEEP_DAYS`; the order lines in `decisions.jsonl` are never pruned.

**Schedule and cost.** Registry job `markets-day` (`newsroom markets day`), `flags.DAY_RUN_HOURS` (8, 14, 20) at minute 40 UTC, outside 05:00-07:00. Spend class `capped`, priority 1 (editorial), not `paid`: the paid class is daily-only
(`ops/products/validate.py`), exactly the reason `markets-fast` is `capped`; `markets day` applies the same gate (`schedule._may_spend`: kill switch, runner claim, spend halt). Expected ~$0.08-0.12 a run, ~$0.25-0.35 a day, hard ceiling $0.45
(an estimate until `day_runs.jsonl` has measured usd). Settlement and mark-to-market happen on every `markets` refresh (every 4 h) and at each run.

**Page layout (10-24 redesign).** `/intel/track-record` opens with ONE portfolio-value chart (`components/track/Portfolio.tsx` `ValueChart`: a line per bot, each labelled at its end with name and value in its own colour, dotted $10,000 start) and ONE summary row per bot (`Books`: value, P&L $ and %, open, cash, trades, win rate or `n=3, too early`, last run) that expands to its open positions (Polymarket link, side, entry, live price "as of HH:MM" from our newest snapshot, stake, unrealised P&L, resolves date plus time left, reason on expand), its trades (with reason) and, for the day bot, its latest run and wishes. No client-side price fetch: the page is server-rendered on an hourly cache, so "now" is the snapshot (the mirror refresh runs every 4 h). Everything else is collapsed (`Fold`): forecast quality, evidence, gaps and wishes, day horizons, misses, resolved, scoring notes; each chart (`ChartCard`) has a question title, a reading guide and renders "Too early: n of 30 markets needed" below the verdict threshold. Tables become stacked labelled rows under 720 px. Additive fields: `now_at` on positions, `last_at` on every book.

**Page.** Additive `day` object in `ohmega.track-record/2`: stats, equity curve, open positions with `ends_at`/`hours_left` (every book's positions carry these now), trade log with reasons (`hours_to_end`), closed trades by hold
horizon (`DAY_HORIZON_BUCKETS`) and category with win rate and P&L withheld below `MIN_RESOLVED_FOR_VERDICT`, the last `DAY_RUNS_SHOWN` runs ("what it browsed and why"), "What it wished we knew", and the watchlist (parsed, not yet drawn).
Parser `lib/track-record.ts` (`parseDay`), components `components/track/DayBook.tsx`, checked by `scripts/contract-check.mjs` through `tests/test_site_contracts.py`.

## Evidence on the page (`research_report.py`)
Additive fields of `ohmega.track-record/2` (no major bump: optional, parsers default them): `evidence` (coverage = share of rated decisions that found the corpus sufficient vs thin vs
gap, citations per decision, tool usage from the traces, `top_gaps` with their status open/tried/filled, accuracy split by evidence richness, caps, gap spend), `fast` (shaped like
`trader` plus horizon/cadence), `horizons` (forecast Brier by time to resolution; median days to resolution per book), and each open position carries `evidence` and a `trail`
(the cited items resolved against the corpus, with a same-site link for countries, situations and places). **Richness split:** decisions that cited at least `RICH_MIN_CITED` (3) items
vs fewer, Brier for forecasts and realised P&L for closed positions (attributed to the first buy), and a group's numbers appear only once it holds
`MIN_RESOLVED_FOR_VERDICT` resolved items (the counts always do). The page adds an "Evidence" section, a "What it looked for" gaps list, a collapsible evidence trail per position and
"The fast book" beside the daily trader (comparison table, its own equity curve, time-to-resolution stats). `newsroom markets evidence` prints the same section.

## Retrieval (`backend/algent_backend/retrieval/`)
A general corpus search, not a markets feature: `docs.py` turns every source into citable `Doc`s (`daily:<date>:<theater>` over the last `DAILY_DAYS`, `statement:`,
`sanction:`, `calendar:`, `geo:` status events; profile claims come from `research/corpus.related` under `CLAIMS_K`), `lexical.py` ranks with in-process BM25 (title counted
double, mild recency lift), and `search.Index` is built once per run and queried per market. `evidence.build(..., index=)` appends the best hits the base evidence did not already
show, so **both the forecaster and the trader read it**; the ids are citable. It is blind-safe: the query is the question text, and the daily's `market_view` is never indexed.
Data access is the local stores the desk already writes (the same files the evidence builder read), so no table or migration is needed and nothing depends on one.

**Embeddings (off).** `retrieval/embed.py` is a pluggable dense ranker, `EMBEDDINGS_ENABLED = False` in `retrieval/flags.py`, import-guarded: switched off, or library/model
unavailable, `load()` returns None and retrieval is lexical. When on, the dense ranking (cosine, asymmetric query/document prompts) is fused with BM25 by reciprocal rank, and
document vectors are cached on disk (`retrieval_store/embeddings.jsonl`, `ALGENT_RETRIEVAL_STORE`) so each text is encoded once. No pgvector table is written: at a few thousand short
documents an in-process scan is fast enough, and the system must work without the extension; if the corpus outgrows that, a `vector` table is the next seam behind `Index`.

To enable (the maintainer's steps; nothing in the repo installs anything), on the server inside the backend venv:
1. `pip install torch --index-url https://download.pytorch.org/whl/cpu` then `pip install sentence-transformers` (the CPU torch wheel keeps this to a few hundred MB instead of GBs).
2. `google/embeddinggemma-300m` is a gated Hugging Face model: accept its licence on the model page and give the server an `HF_TOKEN` (a secret: server env only, never the repo).
3. Set `EMBEDDINGS_ENABLED = True` in `backend/algent_backend/retrieval/flags.py`, commit, push. The first run encodes the corpus (a few thousand docs, minutes on 2 vCPU) and caches it.
   Lighter alternative: `pip install fastembed` and `EMBED_BACKEND = "fastembed"` (ONNX; works only if the installed fastembed release supports the model, untested here).
RAM: the 300M-parameter model is ~1.2 GB in fp32 (~0.6 GB in bf16) plus runtime and activations: budget **about 1.5-2 GB resident while the daily runs**, against ~2.4 GB free on the
2 vCPU / 4 GB server. It fits, but not beside another heavy job: `jobs.sh` already serialises paid jobs on one lock and the model lives only inside the daily process.
Disk: ~600 MB model download plus ~15-30 MB of cached vectors.

## Gap research loop (`gap_loop.py`)
Closes the loop on `gaps.fill`: did a research run the bots asked for actually help? A read-only projection (nothing is stored beyond two optional `GapFill` fields) published as the
`loop` block of the evidence section and rendered as "Did the research help?".
- **Linking.** `GapFill.profile_id` is captured at fill time (the id the run prints, else the one the vector determines, `assembly.profile_id_for`; the id is `prof_gap_<topic slug>`).
  Older lines have none, so `gap_loop.link` searches the profile store for a `requested_by: markets` profile written within -1h..+6h of the fill (`GapFill.at` is the job's start)
  whose title matches the topic by the same Jaccard rule as clustering. No match = "unlinked", said plainly. Uptake is matched by corpus id (`profile:<id>`, `claim:<id>:*`, `profile-timeline:<id>:*`).
- **Measures** (after = from the fill until the next run on the same cluster): re-asks on the cluster vs before; later traces that returned and later forecasts/decisions that cited the profile;
  evidence ratings on the fill's markets plus every market that asked the cluster; bot edge over the market price (market Brier minus bot Brier) on markets forecast on both sides of the fill,
  each side shown only at `MIN_RESOLVED_FOR_VERDICT` resolved forecasts, else "too early".
- **Verdict:** `asked again` (>= `LOOP_REASK_MIN` re-asks) > `answered` (cited) > `unlinked` > `too early` (younger than `LOOP_SETTLE_DAYS`, or nothing decided on its markets since) > `unused`.
- **Feedback.** An `asked again` cluster whose latest ok fill is inside `GAP_REFILL_DAYS` and that never had a refill becomes a candidate in `gaps.fill` once, with a brief quoting the re-asks
  (`GapFill.refill = true`; a failed refill still counts as the one). It competes for the same `GAP_FILL_USD_PER_DAY` / `GAP_FILL_MAX_PER_DAY`; no cap was raised. Knobs: `LOOP_*` in `flags.py`.
- **Limits.** `gaps.record` dedupes per market and topic, so only other markets can re-ask; traces are pruned after `TRACE_KEEP_DAYS`, so "returned" is a floor (citations live on the forecast/decision lines).

## Resting limit orders (`resting.py`; paper only)
A bot can leave a limit order (`place_resting` / `cancel_resting` in `day_tools.py`) that waits between its runs. `limit_price` is the all-in price on its own side (slippage included): a buy
fills at or below it, a sell at or above it. The record is `resting_orders.jsonl`, append-only: placed `open`, then each transition (`filled` / `expired` / `cancelled`, with its reason in `note`) is a
new line carrying the whole order, so the last line per id is its state and nothing is rewritten. A FREE pass (`resting.run_pass`, no model call) refreshes the quotes of the markets that carry
open orders, expires orders past `expires_at` or whose market closed, and fills the rest through the same `guards.apply` and `Decision` ledger an immediate order uses (tag `resting`, `order_id` set), so a
fill counts everywhere a fill does, including the per-day minimum (`day._fills_today` reads the store). The caps are checked at placement AND again at the fill: a fill the guards block outright
is `cancelled` with their reason, a trim fills smaller exactly as an immediate order would. The pass only fills against a live snapshot newer than the order and at most `RESTING_MAX_SNAPSHOT_AGE_H` old.
It runs inside `newsroom markets refresh` (every 4 h) and as the hourly free job `markets-resting` (`:55`). Flags: `RESTING_ENABLED`, `RESTING_MAX_OPEN` (6 per book), `RESTING_MAX_HOURS` (48),
`RESTING_MAX_SNAPSHOT_AGE_H` (2), `RESTING_FILLS_SHOWN`. The track record carries each strategy's `resting: {open, fills}`; the page shows them in the bot's detail.

**Before any real-money executor** (none exists; this path never reaches a venue). A real one would need, outside the model: (1) idempotent client order ids (`RestingOrder.id` is deterministic) so a retry
can never double-send; (2) pre-trade risk checks at the venue boundary (size, price band against the live book, per-market and total exposure, cash actually held there), re-run at send time, not trusted
from placement; (3) a kill switch that cancels every open order and blocks new ones, readable by the executor on each pass; (4) reconciliation of our ledger against the venue's fills, positions and balance
every pass, halting on any mismatch rather than papering over it; (5) a human approval gate before an order first leaves the building, then per-order or per-day limits that approval sets; (6) position and
loss limits enforced by the executor itself (the model can ask for anything, as with `guards.py` today); (7) partial fills, rejections and cancels as first-class states of the record, and an
audit trail of every request and response. The paper fill price (quote plus `SLIPPAGE`) is an assumption a real fill would replace with the venue's execution price.

## The daily job
`newsroom markets daily` (`ops/schedule.jobs()["markets-daily"]`, time `markets/flags.DAILY_UTC`, 07:30 UTC, after daily part 1): refresh prices -> blind forecast pass -> rule book
(`paper.run`) -> trader -> mark both books -> publish. A paid step that raises does not stop the free steps after it (the books are still marked and published) and makes the exit
non-zero so the scheduler's single transient retry applies; the retry is safe because forecasts and trades are idempotent per day. It runs through `newsroom schedule run`, so it
inherits the kill switch (`SCHEDULED_PAID_RUNS`), the runner claim, the spend halt and the watchdog (180 min, $15 per run). `infra/server/install_schedules.sh` installs it with the
other paid timers through `newsroom schedule times` (no per-job edit) and `jobs.sh` routes `markets-daily` to the wrapper. Pause it alone:
`sudo systemctl disable --now ohmega-markets-daily.timer`.

## Operating it
`newsroom markets refresh` (mirror + paper + trader settlement + publish; free), `daily` (the paid job above), `trade [--limit N] [--dry-run]`, `forecast [--limit N] [--dry-run]`,
`paper`, `score [--full]`, `list`, `status`, `publish`, `fast [--dry-run]` (the fast book), `day [--dry-run]` (the day book), `gaps [--list]` (fill the most-asked corpus gaps), `evidence` (how the corpus served the bots). Server: `markets-fast` every 4 h (`capped`) and `markets-gaps` 08:45 UTC (`paid`, the fifth operator-authorised paid job, <= $0.50/day) are registry jobs, so `newsroom products table`/`timers` and the installer pick them up. Doctor check `markets` (a good pass within 10 h). The unattended paid jobs are an operator authorisation (`ops/flags.py`,
`infra/server/jobs.sh`); the operator has authorised `markets-daily` as the fourth (`tests/test_ops_schedule.py` pins the set).
