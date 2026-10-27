"""Operator knobs for the experiment lab (checked-in, not .env)."""

RUN_CAP_USD = 0.05          # per-call cap for a live run (the house model under the budget gate); a live run is refused unless --live is given
EVIDENCE_K = 8              # documents each protocol's retrieval policy may show the model (same for every protocol in a controlled run)
BODY_CHARS = 700            # characters of a document shown to the model
CALIBRATION_BINS = 5
# the common question set (qset.py)
SET_MIN_QUESTIONS = 20      # build aims for at least this many (fewer only when the markets store holds fewer eligible ones; the set then says so)
SET_MAX_QUESTIONS = 30
SET_HOURS_BEFORE = 48       # the fixed cutoff: this many hours before the market resolved
SET_RUN_CAP_USD = 0.30      # TOTAL spend allowed per `lab run --set` invocation (on top of the per-call caps under the budget gate); `--cap` overrides, a re-run continues
DUP_JACCARD = 0.8          # origin chains: two texts sharing this much of their 4-word shingles are one voice repeated (origins.py, method origin-chain@1)
