"""Operator knobs for the experiment lab (checked-in, not .env)."""

RUN_CAP_USD = 0.05          # per-call cap for a live run (the house model under the budget gate); a live run is refused unless --live is given
EVIDENCE_K = 8              # documents each protocol's retrieval policy may show the model (same for every protocol in a controlled run)
BODY_CHARS = 700            # characters of a document shown to the model
CALIBRATION_BINS = 5
# the common question set (qset.py)
SET_MIN_QUESTIONS = 20      # build aims for at least this many (fewer only when the markets store holds fewer eligible ones; the set then says so)
SET_MAX_QUESTIONS = 30
SET_HOURS_BEFORE = 48       # the fixed cutoff: this many hours before the market resolved
SET_MULTI_HOURS = (168, 48, 12)   # set version 2 (`lab questions --set build --multi`): a market may give a question at each of these hours before resolution, when a price is on file
SET_RUN_CAP_USD = 0.30      # TOTAL spend allowed per `lab run --set` invocation (on top of the per-call caps under the budget gate); `--cap` overrides, a re-run continues
DUP_JACCARD = 0.8          # origin chains: two texts sharing this much of their 4-word shingles are one voice repeated (origins.py, method origin-chain@1)
ERR_EXTREME_DIST = 0.35     # errors.py: a wrong-side forecast at least this far from 50% (p >= 85% or <= 15%) is tagged extreme/overconfident
ERR_LEAK_BRIER = 0.02       # errors.py: a right-side forecast this sharp that used no relevant evidence is flagged as a possible leak (model memory), a hint for a human
# calibration policies (calibration.py)
CALIB_LAMBDA = 2.0          # ridge strength of the Platt fit, in observations: pulls (slope, intercept) toward (1, 0), so a few questions can only nudge the map
CALIB_MIN_FIT = 12          # fewer resolved forecasts before the cutoff than this: the map is the identity (and says so)
CALIB_MIN_CLASS = 3         # ... or fewer than this many of either outcome
CALIB_A_MAX = 3.0           # the fitted slope on logit(p) stays in [0, this]
CALIB_P_MIN, CALIB_P_MAX = 0.01, 0.99   # a recalibrated probability is kept inside these
# the tournament (tournament.py)
TOURNAMENT_USD = 1.00       # hard budget for one `lab tournament --live`, checked before every model call
TOURNAMENT_FIRST_SLICE = 6  # questions every candidate answers in round one; the slice doubles each round
TOURNAMENT_TIE_EPS = 0.002  # two candidates whose mean Brier-vs-market differs by less than this are tied; the cheaper wins
# the mutation proposer (mutate.py)
MUTATE_CAP_USD = 0.05       # the one paid prompt draft per `lab mutate --live`
MUTATE_BIAS_GAP = 0.20      # a calibration bin whose said and happened differ by this much (n >= MUTATE_BIAS_MIN_N) is a systematic lean worth naming
MUTATE_BIAS_MIN_N = 5
